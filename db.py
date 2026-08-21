"""Hermes Fleet — persistent org-chart data layer.

Companies contain teams; teams contain memberships (a Hermes profile staffed
into the team with a role and, optionally, a reporting line to another
membership on the same team).

Root-anchored, shared across every profile — mirrors ``hermes_cli.kanban_db``
rather than ``hermes_cli.projects_db``'s per-profile pattern, because a
company/team inherently spans multiple profiles (see ``kanban_home()`` for
the same reasoning applied to the kanban board). File: ``<root>/fleet.db``.

``teams.kanban_board_slug`` and ``memberships.profile`` are soft references
(free-text, validated at the CLI/API layer, never enforced as SQL foreign
keys) — ``fleet.db`` and ``kanban.db`` are separate SQLite files, and Hermes
profiles are directories, not database rows. This mirrors
``projects_db.py``'s own ``board_slug`` column.
"""

from __future__ import annotations

import contextlib
import os
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from hermes_cli.sqlite_util import add_column_if_missing, write_txn
from hermes_constants import get_default_hermes_root

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def fleet_home() -> Path:
    """Return the shared Hermes root that anchors ``fleet.db``.

    Resolution order mirrors ``kanban_db.kanban_home()``:

    1. ``HERMES_FLEET_HOME`` env var when set (explicit override for tests
       and unusual deployments).
    2. ``get_default_hermes_root()`` — the shared root even when the active
       profile's ``HERMES_HOME`` is ``<root>/profiles/<name>``.

    Fleet data is shared across profiles **by design**: a company/team
    inherently spans more than one profile. Resolving through the active
    profile's ``HERMES_HOME`` would silently fork the org chart per profile.
    """
    override = os.environ.get("HERMES_FLEET_HOME", "").strip()
    if override:
        return Path(override).expanduser()
    return get_default_hermes_root()


def fleet_db_path() -> Path:
    return fleet_home() / "fleet.db"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS companies (
    id          TEXT PRIMARY KEY,
    slug        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    description TEXT,
    kind        TEXT NOT NULL DEFAULT 'company',
    created_at  INTEGER NOT NULL,
    archived    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS teams (
    id                TEXT PRIMARY KEY,
    company_id        TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    slug              TEXT NOT NULL,
    name              TEXT NOT NULL,
    description       TEXT,
    kanban_board_slug TEXT,
    created_at        INTEGER NOT NULL,
    archived          INTEGER NOT NULL DEFAULT 0,
    UNIQUE(company_id, slug)
);
CREATE INDEX IF NOT EXISTS idx_teams_company ON teams(company_id);

CREATE TABLE IF NOT EXISTS memberships (
    id           TEXT PRIMARY KEY,
    team_id      TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    profile      TEXT NOT NULL,
    role         TEXT,
    reports_to   TEXT REFERENCES memberships(id) ON DELETE SET NULL,
    joined_at    INTEGER NOT NULL,
    UNIQUE(team_id, profile)
);
CREATE INDEX IF NOT EXISTS idx_memberships_team ON memberships(team_id);
CREATE INDEX IF NOT EXISTS idx_memberships_profile ON memberships(profile);
CREATE INDEX IF NOT EXISTS idx_memberships_reports_to ON memberships(reports_to);
"""

# Columns added after v1 — re-applied idempotently on every open so a
# legacy DB upgrades in place. Each entry is (column_name, full_ddl).
_OPTIONAL_COMPANY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("kind", "kind TEXT NOT NULL DEFAULT 'company'"),
)
_OPTIONAL_TEAM_COLUMNS: tuple[tuple[str, str], ...] = ()
_OPTIONAL_MEMBERSHIP_COLUMNS: tuple[tuple[str, str], ...] = ()


def _migrate_add_optional_columns(conn: sqlite3.Connection) -> None:
    for table, columns in (
        ("companies", _OPTIONAL_COMPANY_COLUMNS),
        ("teams", _OPTIONAL_TEAM_COLUMNS),
        ("memberships", _OPTIONAL_MEMBERSHIP_COLUMNS),
    ):
        if not columns:
            continue
        cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for col, ddl in columns:
            if col not in cols:
                add_column_if_missing(conn, table, col, ddl)


# ---------------------------------------------------------------------------
# Slug + id helpers
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-_]{0,63}$")

# Syntax-only mirror of kanban_db._BOARD_SLUG_RE — kept as a local copy
# rather than importing kanban_db, since board binding must stay a soft,
# optional feature that works even when the kanban plugin isn't loaded.
_BOARD_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-_]{0,63}$")


def _slugify(name: str) -> str:
    s = str(name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-_")
    s = s[:64].strip("-_")
    return s or "entry"


def normalize_slug(slug: Optional[str]) -> Optional[str]:
    if slug is None:
        return None
    s = str(slug).strip().lower()
    if not s:
        return None
    if not _SLUG_RE.match(s):
        raise ValueError(
            f"invalid slug {slug!r}: must be 1-64 chars, lowercase "
            f"alphanumerics / hyphens / underscores, not starting with "
            f"'-' or '_'"
        )
    return s


def normalize_board_slug(slug: Optional[str]) -> Optional[str]:
    """Syntax-only validation for a bound kanban board slug (soft reference)."""
    if slug is None:
        return None
    s = str(slug).strip().lower()
    if not s:
        return None
    if not _BOARD_SLUG_RE.match(s):
        raise ValueError(
            f"invalid board slug {slug!r}: must be 1-64 chars, lowercase "
            f"alphanumerics / hyphens / underscores, not starting with "
            f"'-' or '_'"
        )
    return s


# A company's "kind" is a display/classification tag only — it does not
# change hierarchy behavior (a "group" or "team"-kind top-level entity can
# still contain nested teams the same as a "company"-kind one).
VALID_COMPANY_KINDS = ("company", "team", "group")
DEFAULT_COMPANY_KIND = "company"


def normalize_company_kind(kind: Optional[str]) -> str:
    resolved = (kind or DEFAULT_COMPANY_KIND).strip().lower()
    if resolved not in VALID_COMPANY_KINDS:
        raise ValueError(
            f"invalid company kind {kind!r}: must be one of {', '.join(VALID_COMPANY_KINDS)}"
        )
    return resolved


def _new_company_id() -> str:
    return "c_" + secrets.token_hex(4)


def _new_team_id() -> str:
    return "t_" + secrets.token_hex(4)


def _new_membership_id() -> str:
    return "m_" + secrets.token_hex(4)


def _now() -> int:
    return int(time.time())


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

_INITIALIZED_PATHS: set[str] = set()


def connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Open (and initialize if needed) the shared fleet DB.

    WAL with DELETE fallback for network filesystems (shared helper from
    ``hermes_state``, same as ``projects_db.connect()``). Schema init is
    idempotent (``CREATE TABLE IF NOT EXISTS`` + additive migrations) and
    cached per-path per-process.
    """
    path = db_path if db_path is not None else fleet_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    resolved = str(path.resolve())
    conn = sqlite3.connect(str(path))
    try:
        conn.row_factory = sqlite3.Row
        from hermes_state import apply_wal_with_fallback

        apply_wal_with_fallback(conn, db_label="fleet.db")
        conn.execute("PRAGMA foreign_keys=ON")
        if resolved not in _INITIALIZED_PATHS:
            conn.executescript(SCHEMA_SQL)
            _migrate_add_optional_columns(conn)
            _INITIALIZED_PATHS.add(resolved)
    except Exception:
        conn.close()
        raise
    return conn


@contextlib.contextmanager
def connect_closing(db_path: Optional[Path] = None):
    """Open a fleet DB connection and guarantee it is closed on exit."""
    conn = connect(db_path=db_path)
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass


def init_db(db_path: Optional[Path] = None) -> None:
    """Idempotently ensure the schema exists, without holding the connection open."""
    with connect_closing(db_path=db_path):
        pass


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Membership:
    id: str
    team_id: str
    profile: str
    joined_at: int
    role: Optional[str] = None
    reports_to: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "team_id": self.team_id,
            "profile": self.profile,
            "role": self.role,
            "reports_to": self.reports_to,
            "joined_at": self.joined_at,
        }


@dataclass
class Team:
    id: str
    company_id: str
    slug: str
    name: str
    created_at: int
    description: Optional[str] = None
    kanban_board_slug: Optional[str] = None
    archived: bool = False
    members: List[Membership] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "company_id": self.company_id,
            "slug": self.slug,
            "name": self.name,
            "description": self.description,
            "kanban_board_slug": self.kanban_board_slug,
            "archived": bool(self.archived),
            "created_at": self.created_at,
            "members": [m.to_dict() for m in self.members],
        }


@dataclass
class Company:
    id: str
    slug: str
    name: str
    created_at: int
    description: Optional[str] = None
    kind: str = DEFAULT_COMPANY_KIND
    archived: bool = False
    teams: List[Team] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "slug": self.slug,
            "name": self.name,
            "description": self.description,
            "kind": self.kind,
            "archived": bool(self.archived),
            "created_at": self.created_at,
            "teams": [t.to_dict() for t in self.teams],
        }


def _company_from_row(row: sqlite3.Row) -> Company:
    return Company(
        id=row["id"],
        slug=row["slug"],
        name=row["name"],
        description=row["description"],
        kind=row["kind"] if "kind" in row.keys() else DEFAULT_COMPANY_KIND,
        archived=bool(row["archived"]),
        created_at=row["created_at"],
    )


def _team_from_row(row: sqlite3.Row) -> Team:
    return Team(
        id=row["id"],
        company_id=row["company_id"],
        slug=row["slug"],
        name=row["name"],
        description=row["description"],
        kanban_board_slug=row["kanban_board_slug"],
        archived=bool(row["archived"]),
        created_at=row["created_at"],
    )


def _membership_from_row(row: sqlite3.Row) -> Membership:
    return Membership(
        id=row["id"],
        team_id=row["team_id"],
        profile=row["profile"],
        role=row["role"],
        reports_to=row["reports_to"],
        joined_at=row["joined_at"],
    )


# ---------------------------------------------------------------------------
# Company CRUD
# ---------------------------------------------------------------------------


def create_company(
    conn: sqlite3.Connection,
    *,
    name: str,
    slug: Optional[str] = None,
    description: Optional[str] = None,
    kind: Optional[str] = None,
) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError("company name is required")
    resolved_kind = normalize_company_kind(kind)
    resolved_slug = normalize_slug(slug) if slug else _slugify(name)
    company_id = _new_company_id()
    with write_txn(conn):
        try:
            conn.execute(
                "INSERT INTO companies (id, slug, name, description, kind, created_at, archived) "
                "VALUES (?, ?, ?, ?, ?, ?, 0)",
                (company_id, resolved_slug, name, description, resolved_kind, _now()),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"company slug {resolved_slug!r} already exists") from exc
    return company_id


def get_company(conn: sqlite3.Connection, slug: str, *, with_teams: bool = False) -> Optional[Company]:
    row = conn.execute("SELECT * FROM companies WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        return None
    company = _company_from_row(row)
    if with_teams:
        company.teams = list_teams(conn, company_slug=slug, with_members=True)
    return company


def get_company_by_id(conn: sqlite3.Connection, company_id: str) -> Optional[Company]:
    row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    return _company_from_row(row) if row is not None else None


def list_companies(conn: sqlite3.Connection, *, include_archived: bool = False) -> List[Company]:
    if include_archived:
        rows = conn.execute("SELECT * FROM companies ORDER BY name").fetchall()
    else:
        rows = conn.execute("SELECT * FROM companies WHERE archived = 0 ORDER BY name").fetchall()
    return [_company_from_row(r) for r in rows]


def rename_company(conn: sqlite3.Connection, slug: str, new_name: str) -> None:
    new_name = (new_name or "").strip()
    if not new_name:
        raise ValueError("new company name is required")
    with write_txn(conn):
        cur = conn.execute("UPDATE companies SET name = ? WHERE slug = ?", (new_name, slug))
        if cur.rowcount == 0:
            raise ValueError(f"unknown company: {slug}")


def delete_company(conn: sqlite3.Connection, slug: str, *, force: bool = False) -> None:
    company = get_company(conn, slug)
    if company is None:
        raise ValueError(f"unknown company: {slug}")
    team_count = conn.execute(
        "SELECT COUNT(*) AS n FROM teams WHERE company_id = ?", (company.id,)
    ).fetchone()["n"]
    if team_count and not force:
        raise ValueError(
            f"company {slug!r} has {team_count} team(s); pass force=True to delete anyway"
        )
    with write_txn(conn):
        conn.execute("DELETE FROM companies WHERE id = ?", (company.id,))


# ---------------------------------------------------------------------------
# Team CRUD
# ---------------------------------------------------------------------------


def _require_company(conn: sqlite3.Connection, company_slug: str) -> Company:
    company = get_company(conn, company_slug)
    if company is None:
        raise ValueError(f"unknown company: {company_slug}")
    return company


def create_team(
    conn: sqlite3.Connection,
    *,
    company_slug: str,
    name: str,
    slug: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError("team name is required")
    company = _require_company(conn, company_slug)
    resolved_slug = normalize_slug(slug) if slug else _slugify(name)
    team_id = _new_team_id()
    with write_txn(conn):
        try:
            conn.execute(
                "INSERT INTO teams (id, company_id, slug, name, description, created_at, archived) "
                "VALUES (?, ?, ?, ?, ?, ?, 0)",
                (team_id, company.id, resolved_slug, name, description, _now()),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"team slug {resolved_slug!r} already exists in company {company_slug!r}"
            ) from exc
    return team_id


def get_team(
    conn: sqlite3.Connection, company_slug: str, team_slug: str, *, with_members: bool = False
) -> Optional[Team]:
    company = get_company(conn, company_slug)
    if company is None:
        return None
    row = conn.execute(
        "SELECT * FROM teams WHERE company_id = ? AND slug = ?", (company.id, team_slug)
    ).fetchone()
    if row is None:
        return None
    team = _team_from_row(row)
    if with_members:
        team.members = list_members(conn, team.id)
    return team


def get_team_by_id(conn: sqlite3.Connection, team_id: str) -> Optional[Team]:
    row = conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
    return _team_from_row(row) if row is not None else None


def _require_team(conn: sqlite3.Connection, company_slug: str, team_slug: str) -> Team:
    team = get_team(conn, company_slug, team_slug)
    if team is None:
        raise ValueError(f"unknown team: {team_slug!r} in company {company_slug!r}")
    return team


def list_teams(
    conn: sqlite3.Connection, *, company_slug: Optional[str] = None, with_members: bool = False
) -> List[Team]:
    if company_slug:
        company = get_company(conn, company_slug)
        if company is None:
            return []
        rows = conn.execute(
            "SELECT * FROM teams WHERE company_id = ? ORDER BY name", (company.id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM teams ORDER BY name").fetchall()
    teams = [_team_from_row(r) for r in rows]
    if with_members:
        for team in teams:
            team.members = list_members(conn, team.id)
    return teams


def rename_team(conn: sqlite3.Connection, company_slug: str, team_slug: str, new_name: str) -> None:
    new_name = (new_name or "").strip()
    if not new_name:
        raise ValueError("new team name is required")
    team = _require_team(conn, company_slug, team_slug)
    with write_txn(conn):
        conn.execute("UPDATE teams SET name = ? WHERE id = ?", (new_name, team.id))


def delete_team(conn: sqlite3.Connection, company_slug: str, team_slug: str, *, force: bool = False) -> None:
    team = _require_team(conn, company_slug, team_slug)
    member_count = conn.execute(
        "SELECT COUNT(*) AS n FROM memberships WHERE team_id = ?", (team.id,)
    ).fetchone()["n"]
    if member_count and not force:
        raise ValueError(
            f"team {team_slug!r} has {member_count} member(s); pass force=True to delete anyway"
        )
    with write_txn(conn):
        conn.execute("DELETE FROM teams WHERE id = ?", (team.id,))


def set_team_board(conn: sqlite3.Connection, company_slug: str, team_slug: str, board_slug: Optional[str]) -> None:
    """Bind (or clear, with ``board_slug=None``) a team's linked kanban board.

    ``board_slug`` is a soft reference — only syntax is validated here.
    Existence should be checked by the caller (CLI/API layer) via
    ``hermes_cli.kanban_db.board_exists`` and surfaced as a warning, not a
    hard failure, since the kanban plugin may not even be loaded.
    """
    team = _require_team(conn, company_slug, team_slug)
    normalized = normalize_board_slug(board_slug) if board_slug else None
    with write_txn(conn):
        conn.execute("UPDATE teams SET kanban_board_slug = ? WHERE id = ?", (normalized, team.id))


# ---------------------------------------------------------------------------
# Membership CRUD
# ---------------------------------------------------------------------------


def list_members(conn: sqlite3.Connection, team_id: str) -> List[Membership]:
    rows = conn.execute(
        "SELECT * FROM memberships WHERE team_id = ? ORDER BY joined_at", (team_id,)
    ).fetchall()
    return [_membership_from_row(r) for r in rows]


def add_member(
    conn: sqlite3.Connection,
    company_slug: str,
    team_slug: str,
    profile: str,
    *,
    role: Optional[str] = None,
    reports_to: Optional[str] = None,
) -> str:
    """Add *profile* to a team. ``reports_to`` is another profile already on
    the same team; resolved to that profile's membership id."""
    profile = (profile or "").strip()
    if not profile:
        raise ValueError("profile is required")
    team = _require_team(conn, company_slug, team_slug)

    reports_to_membership_id: Optional[str] = None
    if reports_to:
        manager_row = conn.execute(
            "SELECT id FROM memberships WHERE team_id = ? AND profile = ?",
            (team.id, reports_to),
        ).fetchone()
        if manager_row is None:
            raise ValueError(
                f"reports-to profile {reports_to!r} is not a member of team {team_slug!r} "
                f"(add them first)"
            )
        reports_to_membership_id = manager_row["id"]

    membership_id = _new_membership_id()
    with write_txn(conn):
        try:
            conn.execute(
                "INSERT INTO memberships (id, team_id, profile, role, reports_to, joined_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (membership_id, team.id, profile, role, reports_to_membership_id, _now()),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"{profile!r} is already a member of team {team_slug!r}") from exc
    return membership_id


def remove_member(conn: sqlite3.Connection, company_slug: str, team_slug: str, profile: str) -> None:
    team = _require_team(conn, company_slug, team_slug)
    with write_txn(conn):
        cur = conn.execute(
            "DELETE FROM memberships WHERE team_id = ? AND profile = ?", (team.id, profile)
        )
        if cur.rowcount == 0:
            raise ValueError(f"{profile!r} is not a member of team {team_slug!r}")


# ---------------------------------------------------------------------------
# Org tree
# ---------------------------------------------------------------------------


def org_tree(conn: sqlite3.Connection, *, company_slug: Optional[str] = None) -> List[Company]:
    """Return the full company -> team -> member tree (optionally scoped to
    one company), each membership annotated with its manager's profile name
    for easy rendering."""
    companies = (
        [c for c in [get_company(conn, company_slug)] if c is not None]
        if company_slug
        else list_companies(conn)
    )
    for company in companies:
        company.teams = list_teams(conn, company_slug=company.slug, with_members=True)
    return companies

"""Hermes Fleet dashboard plugin — backend API routes.

Mounted at /api/plugins/hermes-fleet/ by the dashboard plugin system.

This layer is intentionally thin: every handler is a small wrapper around
``db.py`` (the plugin's own data layer), which is the exact same module the
``hermes fleet`` CLI uses. Writes go through the same code paths as the CLI,
so the two surfaces cannot drift.

Security note
-------------
Plugin HTTP routes go through the dashboard's session-token auth middleware
(``web_server.auth_middleware``) automatically, the same as core API routes
and every other plugin's ``/api/plugins/...`` routes — no bespoke auth code
is needed here.

Import note
-----------
This file is loaded standalone by ``web_server._mount_plugin_api_routes``
via ``importlib.util.spec_from_file_location`` with no package context (see
that function's docstring) — a relative ``from . import db`` would fail
here even though it works fine in ``__init__.py``/``cli.py``, which *are*
loaded as part of the plugin's package. So ``db.py`` is loaded directly by
file path below, under a unique module-registry key to avoid colliding with
any other plugin that happens to also ship a module named ``db``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Optional

try:
    from fastapi import APIRouter, HTTPException, Query
except Exception:  # Allows local unit tests without dashboard dependencies.
    class APIRouter:  # type: ignore
        def get(self, *_args, **_kwargs):
            return lambda fn: fn
        def post(self, *_args, **_kwargs):
            return lambda fn: fn
        def patch(self, *_args, **_kwargs):
            return lambda fn: fn
        def delete(self, *_args, **_kwargs):
            return lambda fn: fn

    class HTTPException(Exception):  # type: ignore
        def __init__(self, status_code: int, detail: str = ""):
            self.status_code = status_code
            self.detail = detail

    def Query(default=None, **_kwargs):  # type: ignore
        return default

from pydantic import BaseModel

_DB_PATH = Path(__file__).resolve().parent.parent / "db.py"
_spec = importlib.util.spec_from_file_location("hermes_fleet_db", _DB_PATH)
fleet_db = importlib.util.module_from_spec(_spec)
sys.modules["hermes_fleet_db"] = fleet_db
_spec.loader.exec_module(fleet_db)

router = APIRouter()


def _conn():
    fleet_db.init_db()
    return fleet_db.connect()


def _resolve_board_warning(board_slug: Optional[str]) -> Optional[str]:
    """Best-effort soft-existence check; never raises (kanban may not be loaded)."""
    if not board_slug:
        return None
    try:
        from hermes_cli import kanban_db
    except ImportError:
        return None
    try:
        if not kanban_db.board_exists(board_slug):
            return f"kanban board {board_slug!r} does not exist yet"
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------


class CreateCompanyBody(BaseModel):
    name: str
    slug: Optional[str] = None
    description: Optional[str] = None
    kind: Optional[str] = None


class RenameCompanyBody(BaseModel):
    name: str


@router.get("/companies")
def list_companies(archived: bool = Query(False)):
    conn = _conn()
    try:
        return {"companies": [c.to_dict() for c in fleet_db.list_companies(conn, include_archived=archived)]}
    finally:
        conn.close()


@router.post("/companies")
def create_company(payload: CreateCompanyBody):
    conn = _conn()
    try:
        company_id = fleet_db.create_company(
            conn, name=payload.name, slug=payload.slug, description=payload.description, kind=payload.kind
        )
        company = fleet_db.get_company_by_id(conn, company_id)
        return {"company": company.to_dict() if company else None}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        conn.close()


@router.get("/companies/{slug}")
def get_company(slug: str):
    conn = _conn()
    try:
        company = fleet_db.get_company(conn, slug, with_teams=True)
        if company is None:
            raise HTTPException(status_code=404, detail=f"unknown company: {slug}")
        return {"company": company.to_dict()}
    finally:
        conn.close()


@router.patch("/companies/{slug}")
def rename_company(slug: str, payload: RenameCompanyBody):
    conn = _conn()
    try:
        fleet_db.rename_company(conn, slug, payload.name)
        company = fleet_db.get_company(conn, slug)
        return {"company": company.to_dict() if company else None}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        conn.close()


@router.delete("/companies/{slug}")
def delete_company(slug: str, force: bool = Query(False)):
    conn = _conn()
    try:
        fleet_db.delete_company(conn, slug, force=force)
        return {"deleted": slug}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------


class CreateTeamBody(BaseModel):
    name: str
    company: str
    slug: Optional[str] = None
    description: Optional[str] = None


class UpdateTeamBody(BaseModel):
    name: Optional[str] = None
    kanban_board_slug: Optional[str] = None
    clear_board: bool = False


@router.get("/teams")
def list_teams(company: Optional[str] = Query(None)):
    conn = _conn()
    try:
        return {"teams": [t.to_dict() for t in fleet_db.list_teams(conn, company_slug=company)]}
    finally:
        conn.close()


@router.post("/teams")
def create_team(payload: CreateTeamBody):
    conn = _conn()
    try:
        team_id = fleet_db.create_team(
            conn,
            company_slug=payload.company,
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
        )
        team = fleet_db.get_team_by_id(conn, team_id)
        return {"team": team.to_dict() if team else None}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        conn.close()


@router.get("/teams/{team_slug}")
def get_team(team_slug: str, company: str = Query(...)):
    conn = _conn()
    try:
        team = fleet_db.get_team(conn, company, team_slug, with_members=True)
        if team is None:
            raise HTTPException(status_code=404, detail=f"unknown team: {team_slug}")
        return {"team": team.to_dict()}
    finally:
        conn.close()


@router.patch("/teams/{team_slug}")
def update_team(team_slug: str, payload: UpdateTeamBody, company: str = Query(...)):
    conn = _conn()
    warning: Optional[str] = None
    try:
        if payload.name:
            fleet_db.rename_team(conn, company, team_slug, payload.name)
        if payload.clear_board:
            fleet_db.set_team_board(conn, company, team_slug, None)
        elif payload.kanban_board_slug:
            warning = _resolve_board_warning(payload.kanban_board_slug)
            fleet_db.set_team_board(conn, company, team_slug, payload.kanban_board_slug)
        team = fleet_db.get_team(conn, company, team_slug, with_members=True)
        body: dict[str, Any] = {"team": team.to_dict() if team else None}
        if warning:
            body["warning"] = warning
        return body
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        conn.close()


@router.delete("/teams/{team_slug}")
def delete_team(team_slug: str, company: str = Query(...), force: bool = Query(False)):
    conn = _conn()
    try:
        fleet_db.delete_team(conn, company, team_slug, force=force)
        return {"deleted": team_slug}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Memberships
# ---------------------------------------------------------------------------


class AddMemberBody(BaseModel):
    profile: str
    role: Optional[str] = None
    reports_to: Optional[str] = None


@router.get("/teams/{team_slug}/members")
def list_members(team_slug: str, company: str = Query(...)):
    conn = _conn()
    try:
        team = fleet_db.get_team(conn, company, team_slug, with_members=True)
        if team is None:
            raise HTTPException(status_code=404, detail=f"unknown team: {team_slug}")
        return {"members": [m.to_dict() for m in team.members]}
    finally:
        conn.close()


@router.post("/teams/{team_slug}/members")
def add_member(team_slug: str, payload: AddMemberBody, company: str = Query(...)):
    conn = _conn()
    try:
        membership_id = fleet_db.add_member(
            conn, company, team_slug, payload.profile, role=payload.role, reports_to=payload.reports_to
        )
        team = fleet_db.get_team(conn, company, team_slug, with_members=True)
        member = next((m for m in team.members if m.id == membership_id), None) if team else None
        return {"member": member.to_dict() if member else None}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        conn.close()


@router.delete("/teams/{team_slug}/members/{profile}")
def remove_member(team_slug: str, profile: str, company: str = Query(...)):
    conn = _conn()
    try:
        fleet_db.remove_member(conn, company, team_slug, profile)
        return {"removed": profile}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Org tree + profile picker
# ---------------------------------------------------------------------------


@router.get("/org")
def get_org(company: Optional[str] = Query(None)):
    conn = _conn()
    try:
        companies = fleet_db.org_tree(conn, company_slug=company)
        return {"companies": [c.to_dict() for c in companies]}
    finally:
        conn.close()


@router.get("/profiles")
def list_profiles():
    try:
        from hermes_cli.profiles import list_profiles as _list_profiles

        return {"profiles": [p.name for p in _list_profiles()]}
    except Exception:
        return {"profiles": []}

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
from dataclasses import asdict
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


class UpdateCompanyBody(BaseModel):
    name: Optional[str] = None
    kanban_board_slug: Optional[str] = None
    clear_board: bool = False


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
def update_company(slug: str, payload: UpdateCompanyBody):
    conn = _conn()
    warning: Optional[str] = None
    try:
        if payload.name:
            fleet_db.rename_company(conn, slug, payload.name)
        if payload.clear_board:
            fleet_db.set_company_board(conn, slug, None)
        elif payload.kanban_board_slug:
            warning = _resolve_board_warning(payload.kanban_board_slug)
            fleet_db.set_company_board(conn, slug, payload.kanban_board_slug)
        company = fleet_db.get_company(conn, slug)
        body: dict[str, Any] = {"company": company.to_dict() if company else None}
        if warning:
            body["warning"] = warning
        return body
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
    workspace_path: Optional[str] = None
    clear_workspace: bool = False
    # Link this team's tasks to an existing project: resolves the project's
    # board_slug (auto-provisioning one on the project the first time, same
    # convention as POST /projects) and binds it as this team's board.
    link_project_id: Optional[str] = None
    unlink_project: bool = False


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
        if payload.clear_workspace:
            fleet_db.set_team_workspace(conn, company, team_slug, None)
        elif payload.workspace_path:
            fleet_db.set_team_workspace(conn, company, team_slug, payload.workspace_path)

        if payload.unlink_project:
            fleet_db.set_team_board(conn, company, team_slug, None)
        elif payload.link_project_id:
            board_slug = _link_team_to_project(conn, company, team_slug, payload.link_project_id)
            fleet_db.set_team_board(conn, company, team_slug, board_slug)
        elif payload.clear_board:
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


def _link_team_to_project(conn, company_slug: str, team_slug: str, project_id: str) -> str:
    """Resolve *project_id* and return the board slug to bind the team to,
    auto-provisioning one on the project if it doesn't have one yet (same
    convention POST /projects uses for a fresh team-targeted project)."""
    try:
        from hermes_cli import projects_db
    except ImportError:
        raise ValueError("projects_db is unavailable")
    with projects_db.connect_closing() as pconn:
        project = projects_db.get_project(pconn, project_id)
        if project is None:
            raise ValueError(f"unknown project: {project_id}")
        board_slug = project.board_slug
        if not board_slug:
            board_slug = f"team-{team_slug}"
            projects_db.update_project(pconn, project.id, board_slug=board_slug)
    return board_slug


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
# Fleet roles (leader, manager, summariser, reflection_coach)
# ---------------------------------------------------------------------------


class SetFleetRoleBody(BaseModel):
    profile: str


@router.get("/fleet-roles")
def list_fleet_roles(company: str = Query(...)):
    conn = _conn()
    try:
        roles = fleet_db.get_fleet_roles(conn, company)
        return {"roles": [r.to_dict() for r in roles]}
    finally:
        conn.close()


@router.post("/fleet-roles/{role_type}")
def set_fleet_role(role_type: str, payload: SetFleetRoleBody, company: str = Query(...)):
    conn = _conn()
    try:
        role_id = fleet_db.set_fleet_role(conn, company, role_type, payload.profile)
        role = fleet_db.get_fleet_role(conn, company, role_type)
        return {"role": role.to_dict() if role else None}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        conn.close()


@router.delete("/fleet-roles/{role_type}")
def remove_fleet_role(role_type: str, company: str = Query(...)):
    conn = _conn()
    try:
        fleet_db.remove_fleet_role(conn, company, role_type)
        return {"removed": role_type}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        conn.close()


@router.get("/fleet-roles/global/{role_type}")
def list_fleet_roles_global(role_type: str):
    conn = _conn()
    try:
        rows = fleet_db.list_all_fleet_roles_by_type(conn, role_type)
        return {"assignments": rows}
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


# ---------------------------------------------------------------------------
# Tasks — read-only proxy into hermes_cli.kanban_db (a separate root-anchored
# store; see db.py's module docstring). Scoped to boards actually linked to a
# fleet team/company OR a project (tasks are shown nested under their
# project in the dashboard, so a project-only board must be included even
# when no team/company points at it), falling back to the default board
# when nothing is linked yet.
# ---------------------------------------------------------------------------

_TASK_STATUS_SORT_ORDER = {
    "blocked": 0,
    "running": 1,
    "ready": 2,
    "todo": 3,
    "scheduled": 4,
    "triage": 5,
    "review": 6,
    "done": 7,
    "archived": 8,
}


def _fleet_board_slugs() -> list[str]:
    conn = _conn()
    try:
        slugs = {row["kanban_board_slug"] for row in fleet_db.list_teams_with_board(conn)}
        slugs |= {row["kanban_board_slug"] for row in fleet_db.list_companies_with_board(conn)}
    finally:
        conn.close()
    try:
        from hermes_cli import projects_db

        with projects_db.connect_closing() as pconn:
            slugs |= {
                p.board_slug for p in projects_db.list_projects(pconn, include_archived=False) if p.board_slug
            }
    except ImportError:
        pass
    if not slugs:
        try:
            from hermes_cli import kanban_db

            slugs = {kanban_db.DEFAULT_BOARD}
        except ImportError:
            slugs = {"default"}
    return sorted(slugs)


@router.get("/tasks")
def list_fleet_tasks():
    try:
        from hermes_cli import kanban_db
    except ImportError:
        return {"tasks": [], "boards": [], "blocked_count": 0}

    tasks: list[dict[str, Any]] = []
    boards = _fleet_board_slugs()
    for slug in boards:
        try:
            with kanban_db.connect_closing(board=slug) as kconn:
                for task in kanban_db.list_tasks(kconn):
                    d = asdict(task)
                    tasks.append({
                        "id": d.get("id"),
                        "title": d.get("title"),
                        "status": d.get("status"),
                        "assignee": d.get("assignee"),
                        "priority": d.get("priority"),
                        "created_at": d.get("created_at"),
                        "board": slug,
                    })
        except Exception:
            # A stale/deleted board link shouldn't take down the whole list.
            continue

    tasks.sort(key=lambda t: (
        _TASK_STATUS_SORT_ORDER.get(t["status"], 99),
        -(t["created_at"] or 0),
    ))
    blocked_count = sum(1 for t in tasks if t["status"] == "blocked")
    return {"tasks": tasks, "boards": boards, "blocked_count": blocked_count}


class CreateTaskBody(BaseModel):
    title: str
    body: Optional[str] = None
    assignee: Optional[str] = None
    project_id: str


@router.post("/tasks")
def create_fleet_task(payload: CreateTaskBody):
    try:
        from hermes_cli import kanban_db, projects_db
    except ImportError:
        raise HTTPException(status_code=503, detail="kanban_db/projects_db unavailable")

    with projects_db.connect_closing() as pconn:
        project = projects_db.get_project(pconn, payload.project_id)
        if project is None:
            raise HTTPException(status_code=400, detail=f"unknown project: {payload.project_id}")
        board_slug = project.board_slug
        if not board_slug:
            board_slug = f"project-{project.slug}"
            projects_db.update_project(pconn, project.id, board_slug=board_slug)

    with kanban_db.connect_closing(board=board_slug) as kconn:
        task_id = kanban_db.create_task(
            kconn,
            title=payload.title,
            body=payload.body,
            assignee=payload.assignee or None,
            created_by="hermes-fleet",
        )
    return {"task_id": task_id, "board_slug": board_slug}


# ---------------------------------------------------------------------------
# Projects — read/write proxy into hermes_cli.projects_db (per-profile
# store), cross-referenced against fleet companies/teams via the shared
# board_slug so each project shows which team, group, or company owns it.
# A project can be assigned at either level: to one specific team, or to a
# whole fleet (company/group) directly — see db.py's set_company_board /
# set_team_board, both soft references to the same kanban board namespace.
# ---------------------------------------------------------------------------


def _board_assignment_maps(conn) -> tuple[dict, dict]:
    board_to_team = {row["kanban_board_slug"]: row for row in fleet_db.list_teams_with_board(conn)}
    board_to_company = {row["kanban_board_slug"]: row for row in fleet_db.list_companies_with_board(conn)}
    return board_to_team, board_to_company


def _resolve_assignment(board_slug: Optional[str], board_to_team: dict, board_to_company: dict) -> Optional[dict]:
    if not board_slug:
        return None
    team_row = board_to_team.get(board_slug)
    if team_row:
        return {
            "type": "team",
            "team_slug": team_row["team_slug"],
            "team_name": team_row["team_name"],
            "company_slug": team_row["company_slug"],
            "company_name": team_row["company_name"],
        }
    company_row = board_to_company.get(board_slug)
    if company_row:
        return {
            "type": "company",
            "company_slug": company_row["company_slug"],
            "company_name": company_row["company_name"],
            "company_kind": company_row["company_kind"],
        }
    return None


@router.get("/projects")
def list_fleet_projects():
    try:
        from hermes_cli import projects_db
    except ImportError:
        return {"projects": []}

    with projects_db.connect_closing() as pconn:
        projects = projects_db.list_projects(pconn, include_archived=False)

    conn = _conn()
    try:
        board_to_team, board_to_company = _board_assignment_maps(conn)
    finally:
        conn.close()

    result = []
    for p in projects:
        result.append({
            "id": p.id,
            "slug": p.slug,
            "name": p.name,
            "description": p.description,
            "board_slug": p.board_slug,
            "assignment": _resolve_assignment(p.board_slug, board_to_team, board_to_company),
        })
    return {"projects": result}


class CreateProjectBody(BaseModel):
    name: str
    description: Optional[str] = None
    # Assignment target: "team" binds to one team (needs both slugs below);
    # "company" binds to the whole fleet; omitted/None leaves it unassigned.
    target_type: Optional[str] = None
    target_company_slug: Optional[str] = None
    target_team_slug: Optional[str] = None


@router.post("/projects")
def create_fleet_project(payload: CreateProjectBody):
    try:
        from hermes_cli import projects_db
    except ImportError:
        raise HTTPException(status_code=503, detail="projects_db unavailable")

    board_slug: Optional[str] = None
    if payload.target_type == "team":
        if not (payload.target_company_slug and payload.target_team_slug):
            raise HTTPException(status_code=400, detail="target_company_slug and target_team_slug are required for a team assignment")
        conn = _conn()
        try:
            team = fleet_db.get_team(conn, payload.target_company_slug, payload.target_team_slug)
            if team is None:
                raise HTTPException(status_code=400, detail=f"unknown team: {payload.target_team_slug}")
            board_slug = team.kanban_board_slug
            if not board_slug:
                # First project assigned to this team — provision a board slug
                # from the team's own slug so future projects on the same
                # team reuse it (board_slug doubles as the assignment key).
                board_slug = "team-" + team.slug
                fleet_db.set_team_board(conn, payload.target_company_slug, team.slug, board_slug)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        finally:
            conn.close()
    elif payload.target_type == "company":
        if not payload.target_company_slug:
            raise HTTPException(status_code=400, detail="target_company_slug is required for a company assignment")
        conn = _conn()
        try:
            company = fleet_db.get_company(conn, payload.target_company_slug)
            if company is None:
                raise HTTPException(status_code=400, detail=f"unknown fleet: {payload.target_company_slug}")
            board_slug = company.kanban_board_slug
            if not board_slug:
                board_slug = "co-" + company.slug
                fleet_db.set_company_board(conn, company.slug, board_slug)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        finally:
            conn.close()

    with projects_db.connect_closing() as pconn:
        try:
            project_id = projects_db.create_project(
                pconn, name=payload.name, description=payload.description, board_slug=board_slug,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    return {"project_id": project_id, "board_slug": board_slug}


# ---------------------------------------------------------------------------
# Kanban boards — read-only proxy so the "assign a board" control can offer
# real board slugs instead of free text. Direct board assignment already had
# full CRUD via UpdateTeamBody.kanban_board_slug; this only adds discovery.
# ---------------------------------------------------------------------------


@router.get("/boards")
def list_kanban_boards():
    try:
        from hermes_cli import kanban_db
    except ImportError:
        return {"boards": []}
    try:
        boards = kanban_db.list_boards(include_archived=False)
    except Exception:
        return {"boards": []}
    return {"boards": [{"slug": b.get("slug"), "name": b.get("name") or b.get("slug")} for b in boards]}


# ---------------------------------------------------------------------------
# Team <-> project assignment (many-to-one: several projects can share one
# team's board). Distinct from UpdateTeamBody.link_project_id, which instead
# *rebinds the team's own board* to match one chosen project — that's a
# single exclusive link; this is additive and never touches the team's board
# beyond auto-provisioning one the first time if it has none.
# ---------------------------------------------------------------------------


class AssignProjectBody(BaseModel):
    project_id: str


@router.post("/teams/{team_slug}/projects")
def assign_project_to_team(team_slug: str, payload: AssignProjectBody, company: str = Query(...)):
    conn = _conn()
    try:
        team = fleet_db.get_team(conn, company, team_slug)
        if team is None:
            raise HTTPException(status_code=400, detail=f"unknown team: {team_slug}")
        board_slug = team.kanban_board_slug
        if not board_slug:
            board_slug = f"team-{team_slug}"
            fleet_db.set_team_board(conn, company, team_slug, board_slug)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        conn.close()

    try:
        from hermes_cli import projects_db
    except ImportError:
        raise HTTPException(status_code=503, detail="projects_db unavailable")
    with projects_db.connect_closing() as pconn:
        project = projects_db.get_project(pconn, payload.project_id)
        if project is None:
            raise HTTPException(status_code=400, detail=f"unknown project: {payload.project_id}")
        projects_db.update_project(pconn, project.id, board_slug=board_slug)
    return {"ok": True, "board_slug": board_slug}


@router.delete("/teams/{team_slug}/projects/{project_id}")
def unassign_project_from_team(team_slug: str, project_id: str, company: str = Query(...)):
    # company/team_slug are for URL symmetry with the other team-scoped
    # routes; unassignment just clears whatever board the project currently
    # has, regardless of which team it matched — a project only ever
    # belongs to one board at a time, so there's nothing else to disambiguate.
    try:
        from hermes_cli import projects_db
    except ImportError:
        raise HTTPException(status_code=503, detail="projects_db unavailable")
    with projects_db.connect_closing() as pconn:
        project = projects_db.get_project(pconn, project_id)
        if project is None:
            raise HTTPException(status_code=400, detail=f"unknown project: {project_id}")
        projects_db.update_project(pconn, project.id, board_slug="")
    return {"ok": True}

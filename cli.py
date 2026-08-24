"""CLI commands for the Hermes Legion plugin (``hermes fleet ...``)."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from . import db as fleet_db


def register_cli(subparser: argparse.ArgumentParser) -> None:
    subs = subparser.add_subparsers(dest="fleet_action")

    # -- company ------------------------------------------------------------
    p_company = subs.add_parser("company", help="Manage companies")
    company_sub = p_company.add_subparsers(dest="fleet_company_action")

    c_create = company_sub.add_parser("create", help="Create a company")
    c_create.add_argument("name")
    c_create.add_argument("--slug", default=None)
    c_create.add_argument("--description", default=None)
    c_create.add_argument("--kind", choices=fleet_db.VALID_COMPANY_KINDS, default=None)

    c_list = company_sub.add_parser("list", help="List companies")
    c_list.add_argument("--json", action="store_true")
    c_list.add_argument("--archived", action="store_true", help="Include archived companies")

    c_show = company_sub.add_parser("show", help="Show a company and its teams")
    c_show.add_argument("slug")
    c_show.add_argument("--json", action="store_true")

    c_rename = company_sub.add_parser("rename", help="Rename a company")
    c_rename.add_argument("slug")
    c_rename.add_argument("new_name")

    c_delete = company_sub.add_parser("delete", help="Delete a company")
    c_delete.add_argument("slug")
    c_delete.add_argument("--force", action="store_true", help="Delete even if it has teams")

    c_link = company_sub.add_parser("link-board", help="Bind a fleet (company) to a kanban board")
    c_link.add_argument("slug")
    c_link.add_argument("board_slug")

    c_unlink = company_sub.add_parser("unlink-board", help="Unbind a fleet's kanban board")
    c_unlink.add_argument("slug")

    # -- team -----------------------------------------------------------------
    p_team = subs.add_parser("team", help="Manage teams")
    team_sub = p_team.add_subparsers(dest="fleet_team_action")

    t_create = team_sub.add_parser("create", help="Create a team")
    t_create.add_argument("name")
    t_create.add_argument("--company", required=True)
    t_create.add_argument("--slug", default=None)
    t_create.add_argument("--description", default=None)

    t_list = team_sub.add_parser("list", help="List teams")
    t_list.add_argument("--company", default=None)
    t_list.add_argument("--json", action="store_true")

    t_show = team_sub.add_parser("show", help="Show a team and its members")
    t_show.add_argument("team_slug")
    t_show.add_argument("--company", required=True)
    t_show.add_argument("--json", action="store_true")

    t_rename = team_sub.add_parser("rename", help="Rename a team")
    t_rename.add_argument("team_slug")
    t_rename.add_argument("--company", required=True)
    t_rename.add_argument("new_name")

    t_delete = team_sub.add_parser("delete", help="Delete a team")
    t_delete.add_argument("team_slug")
    t_delete.add_argument("--company", required=True)
    t_delete.add_argument("--force", action="store_true", help="Delete even if it has members")

    t_add = team_sub.add_parser("add-member", help="Add a profile to a team")
    t_add.add_argument("team_slug")
    t_add.add_argument("--company", required=True)
    t_add.add_argument("profile")
    t_add.add_argument("--role", default=None)
    t_add.add_argument("--reports-to", default=None, help="Profile of the manager (must already be on the team)")

    t_remove = team_sub.add_parser("remove-member", help="Remove a profile from a team")
    t_remove.add_argument("team_slug")
    t_remove.add_argument("--company", required=True)
    t_remove.add_argument("profile")

    t_members = team_sub.add_parser("members", help="List a team's members")
    t_members.add_argument("team_slug")
    t_members.add_argument("--company", required=True)
    t_members.add_argument("--json", action="store_true")

    t_link = team_sub.add_parser("link-board", help="Bind a team to a kanban board")
    t_link.add_argument("team_slug")
    t_link.add_argument("--company", required=True)
    t_link.add_argument("board_slug")

    t_unlink = team_sub.add_parser("unlink-board", help="Unbind a team's kanban board")
    t_unlink.add_argument("team_slug")
    t_unlink.add_argument("--company", required=True)

    t_workspace = team_sub.add_parser("set-workspace", help="Set a team's workspace folder")
    t_workspace.add_argument("team_slug")
    t_workspace.add_argument("--company", required=True)
    t_workspace.add_argument("path")

    t_unset_workspace = team_sub.add_parser("unset-workspace", help="Clear a team's workspace folder")
    t_unset_workspace.add_argument("team_slug")
    t_unset_workspace.add_argument("--company", required=True)

    t_link_project = team_sub.add_parser("link-project", help="Link a team's tasks to an existing project")
    t_link_project.add_argument("team_slug")
    t_link_project.add_argument("--company", required=True)
    t_link_project.add_argument("project", help="Project id or slug")

    t_unlink_project = team_sub.add_parser("unlink-project", help="Unlink a team's project (clears its board link)")
    t_unlink_project.add_argument("team_slug")
    t_unlink_project.add_argument("--company", required=True)

    t_assign_project = team_sub.add_parser(
        "assign-project", help="Attach an additional project to a team's board (many-to-one)"
    )
    t_assign_project.add_argument("team_slug")
    t_assign_project.add_argument("--company", required=True)
    t_assign_project.add_argument("project", help="Project id or slug")

    t_unassign_project = team_sub.add_parser("unassign-project", help="Detach a project from a team's board")
    t_unassign_project.add_argument("team_slug")
    t_unassign_project.add_argument("--company", required=True)
    t_unassign_project.add_argument("project", help="Project id or slug")

    # -- org ------------------------------------------------------------------
    p_org = subs.add_parser("org", help="Print the full company -> team -> member tree")
    p_org.add_argument("--company", default=None)
    p_org.add_argument("--json", action="store_true")

    # -- fleet-role -----------------------------------------------------------
    p_role = subs.add_parser("fleet-role", help="Manage fleet-level roles (leader, manager, summariser, coach)")
    role_sub = p_role.add_subparsers(dest="fleet_role_action")

    r_set = role_sub.add_parser("set", help="Assign a fleet-level role")
    r_set.add_argument("company_slug")
    r_set.add_argument("role_type", choices=fleet_db.VALID_FLEET_ROLE_TYPES)
    r_set.add_argument("profile")

    r_list = role_sub.add_parser("list", help="List fleet roles for a company")
    r_list.add_argument("company_slug")
    r_list.add_argument("--json", action="store_true")

    r_remove = role_sub.add_parser("remove", help="Remove a fleet-level role")
    r_remove.add_argument("company_slug")
    r_remove.add_argument("role_type", choices=fleet_db.VALID_FLEET_ROLE_TYPES)

    r_show = role_sub.add_parser("show-global", help="Show all assignments of a role type across fleets")
    r_show.add_argument("role_type", choices=fleet_db.VALID_FLEET_ROLE_TYPES)
    r_show.add_argument("--json", action="store_true")

    subparser.set_defaults(func=fleet_command)


def fleet_command(args: argparse.Namespace) -> int:
    action = getattr(args, "fleet_action", None)
    if not action:
        print("Usage: hermes fleet {company|team|org} ...")
        return 2

    try:
        if action == "company":
            return _dispatch_company(args)
        if action == "team":
            return _dispatch_team(args)
        if action == "org":
            _cmd_org(args)
            return 0
        if action == "fleet-role":
            return _dispatch_fleet_role(args)
        print(f"Unknown fleet action: {action}")
        return 2
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1


def _dispatch_company(args: argparse.Namespace) -> int:
    action = getattr(args, "fleet_company_action", None)
    if not action:
        print("Usage: hermes fleet company {create|list|show|rename|delete|link-board|unlink-board}")
        return 2
    handlers = {
        "create": _cmd_company_create,
        "list": _cmd_company_list,
        "show": _cmd_company_show,
        "rename": _cmd_company_rename,
        "delete": _cmd_company_delete,
        "link-board": _cmd_company_link_board,
        "unlink-board": _cmd_company_unlink_board,
    }
    handler = handlers.get(action)
    if handler is None:
        print(f"Unknown company action: {action}")
        return 2
    handler(args)
    return 0


def _dispatch_team(args: argparse.Namespace) -> int:
    action = getattr(args, "fleet_team_action", None)
    if not action:
        print(
            "Usage: hermes fleet team "
            "{create|list|show|rename|delete|add-member|remove-member|members|"
            "link-board|unlink-board|set-workspace|unset-workspace|link-project|unlink-project|"
            "assign-project|unassign-project}"
        )
        return 2
    handlers = {
        "create": _cmd_team_create,
        "list": _cmd_team_list,
        "show": _cmd_team_show,
        "rename": _cmd_team_rename,
        "delete": _cmd_team_delete,
        "add-member": _cmd_team_add_member,
        "remove-member": _cmd_team_remove_member,
        "members": _cmd_team_members,
        "link-board": _cmd_team_link_board,
        "unlink-board": _cmd_team_unlink_board,
        "set-workspace": _cmd_team_set_workspace,
        "unset-workspace": _cmd_team_unset_workspace,
        "link-project": _cmd_team_link_project,
        "unlink-project": _cmd_team_unlink_project,
        "assign-project": _cmd_team_assign_project,
        "unassign-project": _cmd_team_unassign_project,
    }
    handler = handlers.get(action)
    if handler is None:
        print(f"Unknown team action: {action}")
        return 2
    handler(args)
    return 0


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _fmt_company_line(company: fleet_db.Company) -> str:
    tag = " [archived]" if company.archived else ""
    board = f"  (board: {company.kanban_board_slug})" if company.kanban_board_slug else ""
    return f"  ◆ {company.slug}  {company.name}  ({company.kind}){tag}{board}"


def _fmt_team_line(team: fleet_db.Team) -> str:
    tag = " [archived]" if team.archived else ""
    board = f"  (board: {team.kanban_board_slug})" if team.kanban_board_slug else ""
    workspace = f"  (workspace: {team.workspace_path})" if team.workspace_path else ""
    return f"  ◆ {team.slug}  {team.name}{tag}{board}{workspace}"


def _manager_lookup(members: list) -> dict:
    return {m.id: m.profile for m in members}


def _fmt_member_line(member: fleet_db.Membership, managers: dict) -> str:
    role = f" ({member.role})" if member.role else ""
    reports = ""
    if member.reports_to:
        manager_profile = managers.get(member.reports_to)
        if manager_profile:
            reports = f", reports to {manager_profile}"
    return f"    - {member.profile}{role}{reports}"


# ---------------------------------------------------------------------------
# Company commands
# ---------------------------------------------------------------------------


def _cmd_company_create(args: argparse.Namespace) -> None:
    with fleet_db.connect_closing() as conn:
        company_id = fleet_db.create_company(
            conn, name=args.name, slug=args.slug, description=args.description, kind=args.kind
        )
        company = fleet_db.get_company_by_id(conn, company_id)
    print(f"Created company {company.slug!r} ({company_id})" if company else f"Created company ({company_id})")


def _cmd_company_list(args: argparse.Namespace) -> None:
    with fleet_db.connect_closing() as conn:
        companies = fleet_db.list_companies(conn, include_archived=args.archived)
    if args.json:
        _print_json([c.to_dict() for c in companies])
        return
    if not companies:
        print("No companies found.")
        return
    print(f"\n{len(companies)} compan{'y' if len(companies) == 1 else 'ies'}:\n")
    for company in companies:
        print(_fmt_company_line(company))


def _cmd_company_show(args: argparse.Namespace) -> None:
    with fleet_db.connect_closing() as conn:
        company = fleet_db.get_company(conn, args.slug, with_teams=True)
    if company is None:
        print(f"Unknown company: {args.slug}")
        return
    if args.json:
        _print_json(company.to_dict())
        return
    print(f"\n{company.name}  ({company.slug})  [{company.kind}]")
    if company.description:
        print(f"  {company.description}")
    print(f"\n  {len(company.teams)} team(s):")
    for team in company.teams:
        print(_fmt_team_line(team))
        print(f"      {len(team.members)} member(s)")


def _cmd_company_rename(args: argparse.Namespace) -> None:
    with fleet_db.connect_closing() as conn:
        fleet_db.rename_company(conn, args.slug, args.new_name)
    print(f"Renamed {args.slug} -> {args.new_name!r}")


def _cmd_company_delete(args: argparse.Namespace) -> None:
    with fleet_db.connect_closing() as conn:
        fleet_db.delete_company(conn, args.slug, force=args.force)
    print(f"Deleted company: {args.slug}")


def _cmd_company_link_board(args: argparse.Namespace) -> None:
    _warn_if_board_missing(args.board_slug)
    with fleet_db.connect_closing() as conn:
        fleet_db.set_company_board(conn, args.slug, args.board_slug)
    print(f"Linked {args.slug!r} to board {args.board_slug!r}")


def _cmd_company_unlink_board(args: argparse.Namespace) -> None:
    with fleet_db.connect_closing() as conn:
        fleet_db.set_company_board(conn, args.slug, None)
    print(f"Unlinked board from {args.slug!r}")


# ---------------------------------------------------------------------------
# Team commands
# ---------------------------------------------------------------------------


def _cmd_team_create(args: argparse.Namespace) -> None:
    with fleet_db.connect_closing() as conn:
        team_id = fleet_db.create_team(
            conn,
            company_slug=args.company,
            name=args.name,
            slug=args.slug,
            description=args.description,
        )
    print(f"Created team {args.name!r} in {args.company!r} ({team_id})")


def _cmd_team_list(args: argparse.Namespace) -> None:
    with fleet_db.connect_closing() as conn:
        teams = fleet_db.list_teams(conn, company_slug=args.company)
    if args.json:
        _print_json([t.to_dict() for t in teams])
        return
    if not teams:
        print("No teams found.")
        return
    print(f"\n{len(teams)} team(s):\n")
    for team in teams:
        print(_fmt_team_line(team))


def _cmd_team_show(args: argparse.Namespace) -> None:
    with fleet_db.connect_closing() as conn:
        team = fleet_db.get_team(conn, args.company, args.team_slug, with_members=True)
    if team is None:
        print(f"Unknown team: {args.team_slug} in {args.company}")
        return
    if args.json:
        _print_json(team.to_dict())
        return
    print(f"\n{team.name}  ({team.slug})")
    if team.description:
        print(f"  {team.description}")
    if team.kanban_board_slug:
        print(f"  board: {team.kanban_board_slug}")
    if team.workspace_path:
        print(f"  workspace: {team.workspace_path}")
    print(f"\n  {len(team.members)} member(s):")
    managers = _manager_lookup(team.members)
    for member in team.members:
        print(_fmt_member_line(member, managers))


def _cmd_team_rename(args: argparse.Namespace) -> None:
    with fleet_db.connect_closing() as conn:
        fleet_db.rename_team(conn, args.company, args.team_slug, args.new_name)
    print(f"Renamed {args.team_slug} -> {args.new_name!r}")


def _cmd_team_delete(args: argparse.Namespace) -> None:
    with fleet_db.connect_closing() as conn:
        fleet_db.delete_team(conn, args.company, args.team_slug, force=args.force)
    print(f"Deleted team: {args.team_slug}")


def _cmd_team_add_member(args: argparse.Namespace) -> None:
    with fleet_db.connect_closing() as conn:
        membership_id = fleet_db.add_member(
            conn,
            args.company,
            args.team_slug,
            args.profile,
            role=args.role,
            reports_to=args.reports_to,
        )
    print(f"Added {args.profile!r} to {args.team_slug!r} ({membership_id})")


def _cmd_team_remove_member(args: argparse.Namespace) -> None:
    with fleet_db.connect_closing() as conn:
        fleet_db.remove_member(conn, args.company, args.team_slug, args.profile)
    print(f"Removed {args.profile!r} from {args.team_slug!r}")


def _cmd_team_members(args: argparse.Namespace) -> None:
    with fleet_db.connect_closing() as conn:
        team = fleet_db.get_team(conn, args.company, args.team_slug, with_members=True)
    if team is None:
        print(f"Unknown team: {args.team_slug} in {args.company}")
        return
    if args.json:
        _print_json([m.to_dict() for m in team.members])
        return
    if not team.members:
        print("No members found.")
        return
    managers = _manager_lookup(team.members)
    print(f"\n{len(team.members)} member(s) of {team.slug}:\n")
    for member in team.members:
        print(_fmt_member_line(member, managers))


def _cmd_team_link_board(args: argparse.Namespace) -> None:
    _warn_if_board_missing(args.board_slug)
    with fleet_db.connect_closing() as conn:
        fleet_db.set_team_board(conn, args.company, args.team_slug, args.board_slug)
    print(f"Linked {args.team_slug!r} to board {args.board_slug!r}")


def _cmd_team_unlink_board(args: argparse.Namespace) -> None:
    with fleet_db.connect_closing() as conn:
        fleet_db.set_team_board(conn, args.company, args.team_slug, None)
    print(f"Unlinked board from {args.team_slug!r}")


def _warn_if_board_missing(board_slug: str) -> None:
    """Best-effort soft-existence check against the kanban plugin's board
    store. Never raises — the kanban plugin may not be installed/loaded,
    and a not-yet-created board is a legitimate thing to pre-bind."""
    try:
        from hermes_cli import kanban_db
    except ImportError:
        return
    try:
        if not kanban_db.board_exists(board_slug):
            print(f"Warning: kanban board {board_slug!r} does not exist yet.")
    except Exception:
        pass


def _cmd_team_set_workspace(args: argparse.Namespace) -> None:
    if not os.path.isdir(os.path.expanduser(args.path)):
        print(f"Warning: {args.path!r} does not exist on this machine yet.")
    with fleet_db.connect_closing() as conn:
        fleet_db.set_team_workspace(conn, args.company, args.team_slug, args.path)
    print(f"Set workspace for {args.team_slug!r}: {fleet_db.normalize_workspace_path(args.path)}")


def _cmd_team_unset_workspace(args: argparse.Namespace) -> None:
    with fleet_db.connect_closing() as conn:
        fleet_db.set_team_workspace(conn, args.company, args.team_slug, None)
    print(f"Cleared workspace for {args.team_slug!r}")


def _cmd_team_link_project(args: argparse.Namespace) -> None:
    try:
        from hermes_cli import projects_db
    except ImportError:
        print("Error: projects_db is unavailable.")
        return
    with projects_db.connect_closing() as pconn:
        project = projects_db.get_project(pconn, args.project)
        if project is None:
            print(f"Unknown project: {args.project}")
            return
        board_slug = project.board_slug
        if not board_slug:
            board_slug = f"team-{args.team_slug}"
            projects_db.update_project(pconn, project.id, board_slug=board_slug)
    with fleet_db.connect_closing() as conn:
        fleet_db.set_team_board(conn, args.company, args.team_slug, board_slug)
    print(f"Linked {args.team_slug!r} to project {project.slug!r} (board {board_slug!r})")


def _cmd_team_unlink_project(args: argparse.Namespace) -> None:
    with fleet_db.connect_closing() as conn:
        fleet_db.set_team_board(conn, args.company, args.team_slug, None)
    print(f"Unlinked project from {args.team_slug!r}")


def _cmd_team_assign_project(args: argparse.Namespace) -> None:
    """Attach an additional project to a team's board — unlike link-project,
    never rebinds the team's own board, so several projects can be assigned
    to the same team over time."""
    with fleet_db.connect_closing() as conn:
        team = fleet_db.get_team(conn, args.company, args.team_slug)
        if team is None:
            print(f"Unknown team: {args.team_slug} in {args.company}")
            return
        board_slug = team.kanban_board_slug
        if not board_slug:
            board_slug = f"team-{args.team_slug}"
            fleet_db.set_team_board(conn, args.company, args.team_slug, board_slug)

    try:
        from hermes_cli import projects_db
    except ImportError:
        print("Error: projects_db is unavailable.")
        return
    with projects_db.connect_closing() as pconn:
        project = projects_db.get_project(pconn, args.project)
        if project is None:
            print(f"Unknown project: {args.project}")
            return
        projects_db.update_project(pconn, project.id, board_slug=board_slug)
    print(f"Assigned project {project.slug!r} to {args.team_slug!r} (board {board_slug!r})")


def _cmd_team_unassign_project(args: argparse.Namespace) -> None:
    try:
        from hermes_cli import projects_db
    except ImportError:
        print("Error: projects_db is unavailable.")
        return
    with projects_db.connect_closing() as pconn:
        project = projects_db.get_project(pconn, args.project)
        if project is None:
            print(f"Unknown project: {args.project}")
            return
        projects_db.update_project(pconn, project.id, board_slug="")
    print(f"Unassigned project {project.slug!r}")


# ---------------------------------------------------------------------------
# Fleet-role commands
# ---------------------------------------------------------------------------


def _dispatch_fleet_role(args: argparse.Namespace) -> int:
    action = getattr(args, "fleet_role_action", None)
    if not action:
        print("Usage: hermes fleet fleet-role {set|list|remove|show-global}")
        return 2
    handlers = {
        "set": _cmd_fleet_role_set,
        "list": _cmd_fleet_role_list,
        "remove": _cmd_fleet_role_remove,
        "show-global": _cmd_fleet_role_show_global,
    }
    handler = handlers.get(action)
    if handler is None:
        print(f"Unknown fleet-role action: {action}")
        return 2
    try:
        handler(args)
        return 0
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1


def _cmd_fleet_role_set(args: argparse.Namespace) -> None:
    with fleet_db.connect_closing() as conn:
        role_id = fleet_db.set_fleet_role(conn, args.company_slug, args.role_type, args.profile)
    label = fleet_db.VALID_FLEET_ROLE_LABELS.get(args.role_type, args.role_type)
    print(f"Assigned {args.profile!r} as {label} for fleet {args.company_slug!r} ({role_id})")


def _cmd_fleet_role_list(args: argparse.Namespace) -> None:
    with fleet_db.connect_closing() as conn:
        roles = fleet_db.get_fleet_roles(conn, args.company_slug)
    if args.json:
        _print_json([r.to_dict() for r in roles])
        return
    if not roles:
        print(f"No fleet roles assigned for {args.company_slug!r}.")
        return
    print(f"\nFleet roles for {args.company_slug!r}:\n")
    for role in roles:
        label = fleet_db.VALID_FLEET_ROLE_LABELS.get(role.role_type, role.role_type)
        print(f"  {label}: {role.profile}")


def _cmd_fleet_role_remove(args: argparse.Namespace) -> None:
    with fleet_db.connect_closing() as conn:
        fleet_db.remove_fleet_role(conn, args.company_slug, args.role_type)
    label = fleet_db.VALID_FLEET_ROLE_LABELS.get(args.role_type, args.role_type)
    print(f"Removed {label} role from fleet {args.company_slug!r}")


def _cmd_fleet_role_show_global(args: argparse.Namespace) -> None:
    with fleet_db.connect_closing() as conn:
        rows = fleet_db.list_all_fleet_roles_by_type(conn, args.role_type)
    if args.json:
        _print_json(rows)
        return
    label = fleet_db.VALID_FLEET_ROLE_LABELS.get(args.role_type, args.role_type)
    if not rows:
        print(f"No {label} assignments found across any fleet.")
        return
    print(f"\n{label} assignments across all fleets:\n")
    for row in rows:
        print(f"  {row['company_name']} ({row['company_slug']}): {row['profile']}")


# ---------------------------------------------------------------------------
# Org tree
# ---------------------------------------------------------------------------


def _cmd_org(args: argparse.Namespace) -> None:
    with fleet_db.connect_closing() as conn:
        companies = fleet_db.org_tree(conn, company_slug=args.company)
    if args.json:
        _print_json([c.to_dict() for c in companies])
        return
    if not companies:
        print("No companies found.")
        return
    for company in companies:
        print(f"\n{company.name}  ({company.slug})")
        for team in company.teams:
            print(f"  {team.name}  ({team.slug})")
            managers = _manager_lookup(team.members)
            for member in team.members:
                print(_fmt_member_line(member, managers))

"""Hermes Legion plugin — persistent org-chart layer over Hermes agent profiles.

Registers only operator-facing CLI surfaces. The agent should invoke these via
the terminal tool; no model tools are added by this plugin (v1 scope).
"""

from __future__ import annotations

from .cli import register_cli, fleet_command


def register(ctx) -> None:
    ctx.register_cli_command(
        name="fleet",
        help="Manage companies, teams, and profile-to-role assignments",
        setup_fn=register_cli,
        handler_fn=fleet_command,
        description=(
            "Operator CLI for the Hermes Legion org-chart layer: companies, 
            "teams, and memberships (role + reporting line) across Hermes "
            "agent profiles."
        ),
    )

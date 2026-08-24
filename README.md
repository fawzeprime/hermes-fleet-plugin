# Hermes Legion

A Hermes Agent plugin for managing organizational hierarchies — fleets, teams, agents, projects, and reporting lines across your Hermes agent ecosystem.

## Features

### Fleet Management
- Create and manage **fleets** (companies/groups) containing teams of Hermes agents
- Assign agents to teams with roles and reporting lines
- Visual org-chart hierarchy with flowchart rendering

### Fleet Leadership
- Assign a **Leader / CEO** at the top of each fleet's hierarchy
- Assign a **Manager** as second-in-command (reports to CEO, all agents report to Manager)
- Add a **Summariser** and **Reflection Coach** that operate across all fleets

### Project Management
- Create projects and assign them to fleets or individual teams
- Link projects to **workspace folders** and **GitHub repositories**
- Create **sub-projects** with their own task lists
- Attach **documents** to projects (links, files, design specs, meeting notes)
- Kanban board integration for task tracking

### Dashboard
- Fleet overview with agent counts, team stats, and blocked task indicators
- Per-fleet hierarchy flowcharts embedded in the Org Chart view
- Unassigned agent profile detection

## CLI Commands

```bash
# Fleets
hermes fleet company create "Acme Corp"
hermes fleet company list
hermes fleet company show acme-corp

# Teams
hermes fleet team create "Engineering" --company acme-corp
hermes fleet team add-member engineering --company acme-corp seer --role "Lead" --reports-to prophet

# Fleet Roles
hermes fleet fleet-role set acme-corp leader seer
hermes fleet fleet-role set acme-corp manager prophet
hermes fleet fleet-role set acme-corp summariser archivist
hermes fleet fleet-role set acme-corp reflection_coach devops
hermes fleet fleet-role list acme-corp

# Org Chart
hermes fleet org
hermes fleet org --company acme-corp --json
```

## API Endpoints

All routes are mounted at `/api/plugins/hermes-legion/`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/companies` | List all fleets |
| POST | `/companies` | Create a fleet |
| GET | `/companies/{slug}` | Get fleet with teams |
| PATCH | `/companies/{slug}` | Update fleet |
| DELETE | `/companies/{slug}` | Delete fleet |
| GET | `/teams` | List teams |
| POST | `/teams` | Create a team |
| GET | `/teams/{slug}/members` | List team members |
| POST | `/teams/{slug}/members` | Add agent to team |
| POST | `/fleet-roles/{role_type}` | Assign fleet role |
| GET | `/fleet-roles?company=` | List fleet roles |
| DELETE | `/fleet-roles/{role_type}` | Remove fleet role |
| GET | `/org` | Full org tree |
| GET | `/projects` | List projects with extensions |
| POST | `/projects` | Create project |
| PATCH | `/projects/{id}` | Edit project (name, workspace, github) |
| POST | `/projects/{id}/subprojects` | Create sub-project |
| GET | `/projects/{id}/documents` | List project documents |
| POST | `/projects/{id}/documents` | Add document |
| GET | `/tasks` | List tasks across fleet boards |
| POST | `/tasks` | Create task |

## Installation

This is a Hermes Agent plugin. Place it in your Hermes plugins directory and it will be auto-discovered via `plugin.yaml` and `dashboard/manifest.json`.

## Architecture

- **db.py** — SQLite data layer (fleet.db): companies, teams, memberships, fleet roles, project extensions, project documents
- **cli.py** — `hermes fleet` CLI commands
- **dashboard/plugin_api.py** — FastAPI routes mounted by the Hermes dashboard
- **dashboard/dist/index.js** — React-based dashboard UI (no build step)
- **dashboard/dist/style.css** — Styles

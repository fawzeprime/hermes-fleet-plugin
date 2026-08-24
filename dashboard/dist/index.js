/**
 * Hermes Fleet — Dashboard Plugin
 *
 * Org-chart view (companies -> teams -> members) backed by ~/.hermes/fleet.db.
 * Calls the plugin's backend at /api/plugins/hermes-fleet/.
 *
 * Plain IIFE, no build step. Uses window.__HERMES_PLUGIN_SDK__ for React +
 * shadcn primitives, mirroring the kanban dashboard plugin's structure.
 */
(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !window.__HERMES_PLUGINS__) return;

  const { React } = SDK;
  const h = React.createElement;
  const { Card, CardContent, Badge, Button, Input, Label, Select, SelectOption, TabsList, TabsTrigger } = SDK.components;
  const { useState, useEffect, useCallback } = SDK.hooks;
  const { cn } = SDK.utils;

  // Keep in sync with db.VALID_COMPANY_KINDS.
  const COMPANY_KINDS = ["company", "team", "group"];

  // Keep in sync with db.VALID_FLEET_ROLE_TYPES / VALID_FLEET_ROLE_LABELS.
  const FLEET_ROLE_TYPES = ["leader", "manager", "summariser", "reflection_coach"];
  const FLEET_ROLE_LABELS = {
    leader: "Leader / CEO",
    manager: "Manager",
    summariser: "Summariser",
    reflection_coach: "Reflection Coach",
  };
  const GLOBAL_ROLE_TYPES = ["summariser", "reflection_coach"];

  // fetchJSON passes `init` straight through to native fetch() without
  // touching `body` or headers — a JSON string body with no explicit
  // Content-Type defaults to text/plain, which makes the backend's Pydantic
  // model validation see a raw string instead of a parsed object (422:
  // "Input should be a valid dictionary or object"). Set it here once so
  // every POST/PATCH call site doesn't have to remember.
  function api(path, options) {
    const opts = Object.assign({}, options);
    if (opts.body && !opts.headers) {
      opts.headers = { "Content-Type": "application/json" };
    }
    return SDK.fetchJSON("/api/plugins/hermes-fleet" + path, opts);
  }

  // The SDK's Select fires onValueChange(value) directly (shadcn-style
  // popup, not a native <select>), mirroring the kanban dashboard plugin.
  function selectChangeHandler(setter) {
    return { onValueChange: function (v) { setter(v == null ? "" : v); } };
  }

  // ---------------------------------------------------------------------
  // Small inline forms
  // ---------------------------------------------------------------------

  function InlineForm({ onCancel, onSubmit, submitLabel, children }) {
    return h("form", {
      className: "hf-inline-form",
      onSubmit: function (e) {
        e.preventDefault();
        onSubmit();
      },
    },
      children,
      h("div", { className: "hf-inline-form-actions" },
        h(Button, { type: "submit" }, submitLabel),
        h(Button, { type: "button", ghost: true, onClick: onCancel }, "Cancel")
      )
    );
  }

  function AddCompanyForm({ onDone }) {
    const [open, setOpen] = useState(false);
    const [name, setName] = useState("");
    const [description, setDescription] = useState("");
    const [kind, setKind] = useState("company");
    const [error, setError] = useState(null);

    if (!open) {
      return h(Button, { onClick: function () { setOpen(true); } }, "+ Fleet");
    }

    function submit() {
      api("/companies", {
        method: "POST",
        body: JSON.stringify({ name: name, description: description || null, kind: kind }),
      })
        .then(function () { setOpen(false); setName(""); setDescription(""); setKind("company"); setError(null); onDone(); })
        .catch(function (err) { setError(String(err)); });
    }

    return h(InlineForm, { onCancel: function () { setOpen(false); setError(null); }, onSubmit: submit, submitLabel: "Create fleet" },
      h("div", { className: "hf-field" },
        h(Label, null, "Name"),
        h(Input, { value: name, onChange: function (e) { setName(e.target.value); }, autoFocus: true, required: true })
      ),
      h("div", { className: "hf-field" },
        h(Label, null, "Type"),
        h(Select, Object.assign({ value: kind }, selectChangeHandler(setKind)),
          COMPANY_KINDS.map(function (k) {
            return h(SelectOption, { key: k, value: k }, k.charAt(0).toUpperCase() + k.slice(1));
          })
        )
      ),
      h("div", { className: "hf-field" },
        h(Label, null, "Description"),
        h("textarea", {
          className: "hf-textarea",
          value: description,
          onChange: function (e) { setDescription(e.target.value); },
          rows: 4,
        })
      ),
      error && h("div", { className: "hf-error" }, error)
    );
  }

  function AddTeamForm({ companySlug, onDone }) {
    const [open, setOpen] = useState(false);
    const [name, setName] = useState("");
    const [error, setError] = useState(null);

    if (!open) {
      return h(Button, { ghost: true, onClick: function () { setOpen(true); } }, "+ Team");
    }

    function submit() {
      api("/teams", {
        method: "POST",
        body: JSON.stringify({ name: name, company: companySlug }),
      })
        .then(function () { setOpen(false); setName(""); setError(null); onDone(); })
        .catch(function (err) { setError(String(err)); });
    }

    return h(InlineForm, { onCancel: function () { setOpen(false); setError(null); }, onSubmit: submit, submitLabel: "Create team" },
      h("div", { className: "hf-field" },
        h(Label, null, "Team name"),
        h(Input, { value: name, onChange: function (e) { setName(e.target.value); }, autoFocus: true, required: true })
      ),
      error && h("div", { className: "hf-error" }, error)
    );
  }

  function AddMemberForm({ companySlug, teamSlug, existingProfiles, allProfiles, onDone }) {
    const [open, setOpen] = useState(false);
    const [profile, setProfile] = useState("");
    const [role, setRole] = useState("");
    const [reportsTo, setReportsTo] = useState("");
    const [error, setError] = useState(null);

    if (!open) {
      return h(Button, { ghost: true, onClick: function () { setOpen(true); } }, "+ Add agent");
    }

    function submit() {
      api("/teams/" + encodeURIComponent(teamSlug) + "/members?company=" + encodeURIComponent(companySlug), {
        method: "POST",
        body: JSON.stringify({ profile: profile, role: role || null, reports_to: reportsTo || null }),
      })
        .then(function () { setOpen(false); setProfile(""); setRole(""); setReportsTo(""); setError(null); onDone(); })
        .catch(function (err) { setError(String(err)); });
    }

    return h(InlineForm, { onCancel: function () { setOpen(false); setError(null); }, onSubmit: submit, submitLabel: "Add agent" },
      h("div", { className: "hf-field" },
        h(Label, null, "Agent (profile)"),
        h(Input, {
          value: profile,
          onChange: function (e) { setProfile(e.target.value); },
          list: "hf-profile-options",
          placeholder: "e.g. seer",
          autoFocus: true,
          required: true,
        }),
        h("datalist", { id: "hf-profile-options" }, allProfiles.map(function (p) {
          return h("option", { key: p, value: p });
        }))
      ),
      h("div", { className: "hf-field" },
        h(Label, null, "Role"),
        h(Input, { value: role, onChange: function (e) { setRole(e.target.value); }, placeholder: "e.g. Project Manager" })
      ),
      existingProfiles.length > 0 && h("div", { className: "hf-field" },
        h(Label, null, "Reports to (optional)"),
        h(Input, {
          value: reportsTo,
          onChange: function (e) { setReportsTo(e.target.value); },
          list: "hf-manager-options",
          placeholder: "profile on this team",
        }),
        h("datalist", { id: "hf-manager-options" }, existingProfiles.map(function (p) {
          return h("option", { key: p, value: p });
        }))
      ),
      error && h("div", { className: "hf-error" }, error)
    );
  }

  // ---------------------------------------------------------------------
  // Fleet role controls (leader, manager, summariser, reflection_coach)
  // ---------------------------------------------------------------------

  function FleetRoleBadge({ roleType, profile, companySlug, onChanged }) {
    var label = FLEET_ROLE_LABELS[roleType] || roleType;
    return h("div", { className: "hf-fleet-role-badge" },
      h("span", { className: "hf-fleet-role-type" }, label),
      h("span", { className: "hf-fleet-role-profile" }, profile),
      h(Button, {
        ghost: true, destructive: true, className: "hf-fleet-role-remove",
        onClick: function () {
          api("/fleet-roles/" + encodeURIComponent(roleType) + "?company=" + encodeURIComponent(companySlug), { method: "DELETE" })
            .then(onChanged).catch(function (err) { window.alert(String(err)); });
        },
      }, "×")
    );
  }

  function FleetRoleSetForm({ roleType, companySlug, currentProfile, onDone }) {
    const [editing, setEditing] = useState(false);
    const [profile, setProfile] = useState(currentProfile || "");
    const [error, setError] = useState(null);
    var label = FLEET_ROLE_LABELS[roleType] || roleType;

    if (!editing) {
      return h(Button, {
        ghost: true, className: "hf-fleet-role-edit",
        onClick: function () { setProfile(currentProfile || ""); setEditing(true); },
      }, currentProfile ? "Change" : "Assign");
    }

    function save() {
      if (!profile.trim()) { setError("Profile is required"); return; }
      api("/fleet-roles/" + encodeURIComponent(roleType) + "?company=" + encodeURIComponent(companySlug), {
        method: "POST",
        body: JSON.stringify({ profile: profile.trim() }),
      })
        .then(function () { setEditing(false); setError(null); onDone(); })
        .catch(function (err) { setError(String(err)); });
    }

    return h("div", { className: "hf-fleet-role-form" },
      h(Input, {
        value: profile, onChange: function (e) { setProfile(e.target.value); },
        placeholder: "profile name", autoFocus: true,
      }),
      h(Button, { onClick: save }, "Save"),
      h(Button, { ghost: true, onClick: function () { setEditing(false); setError(null); } }, "Cancel"),
      error && h("div", { className: "hf-error" }, error)
    );
  }

  function FleetRolesPanel({ company, onChanged }) {
    var rolesByType = {};
    FLEET_ROLE_TYPES.forEach(function (rt) { rolesByType[rt] = null; });
    (company.fleet_roles || []).forEach(function (r) { rolesByType[r.role_type] = r; });

    return h("div", { className: "hf-fleet-roles" },
      h("div", { className: "hf-fleet-roles-label" }, "Fleet Roles"),
      h("div", { className: "hf-fleet-roles-grid" },
        FLEET_ROLE_TYPES.map(function (rt) {
          var role = rolesByType[rt];
          var label = FLEET_ROLE_LABELS[rt] || rt;
          return h("div", { key: rt, className: "hf-fleet-role-item" },
            role
              ? h(FleetRoleBadge, { roleType: rt, profile: role.profile, companySlug: company.slug, onChanged: onChanged })
              : h("div", { className: "hf-fleet-role-empty" },
                  h("span", { className: "hf-fleet-role-type" }, label),
                  h("span", { className: "hf-empty" }, "Not assigned"),
                  h(FleetRoleSetForm, { roleType: rt, companySlug: company.slug, currentProfile: null, onDone: onChanged })
                ),
            role && h(FleetRoleSetForm, { roleType: rt, companySlug: company.slug, currentProfile: role.profile, onDone: onChanged })
          );
        })
      )
    );
  }

  // Global roles popover (summariser + reflection_coach across all fleets)
  function GlobalRoleOptions({ companies, allProfiles, onChanged }) {
    const [open, setOpen] = useState(false);

    if (!open) {
      return h(Button, { ghost: true, onClick: function () { setOpen(true); } }, "⚙ Options");
    }

    return h(Card, { className: "hf-global-options" },
      h(CardContent, null,
        h("div", { className: "hf-global-options-header" },
          h("h3", null, "Global Fleet Agents"),
          h("p", { className: "hf-description" }, "Summariser and Reflection Coach operate across all fleets."),
          h(Button, { ghost: true, onClick: function () { setOpen(false); } }, "Close")
        ),
        h("div", { className: "hf-global-options-grid" },
          companies.map(function (c) {
            var rolesByType = {};
            (c.fleet_roles || []).forEach(function (r) { rolesByType[r.role_type] = r; });
            return h("div", { key: c.id, className: "hf-global-option-fleet" },
              h("strong", null, c.name),
              h("div", { className: "hf-global-option-roles" },
                GLOBAL_ROLE_TYPES.map(function (rt) {
                  var role = rolesByType[rt];
                  var label = FLEET_ROLE_LABELS[rt] || rt;
                  return h("div", { key: rt, className: "hf-global-option-role" },
                    h("span", { className: "hf-fleet-role-type" }, label),
                    role
                      ? h("span", { className: "hf-fleet-role-profile" }, role.profile)
                      : h("span", { className: "hf-empty" }, "—"),
                    h(FleetRoleSetForm, { roleType: rt, companySlug: c.slug, currentProfile: role ? role.profile : null, onDone: onChanged })
                  );
                })
              )
            );
          })
        )
      )
    );
  }

  // ---------------------------------------------------------------------
  // Tree rendering
  // ---------------------------------------------------------------------

  function managerLookup(members) {
    const byId = {};
    members.forEach(function (m) { byId[m.id] = m.profile; });
    return byId;
  }

  function MemberRow({ member, managers, companySlug, teamSlug, onChanged }) {
    const managerName = member.reports_to ? managers[member.reports_to] : null;
    return h("div", { className: "hf-member" },
      h("span", { className: "hf-member-name" }, member.profile),
      member.role && h(Badge, { tone: "secondary" }, member.role),
      managerName && h("span", { className: "hf-member-reports" }, "reports to " + managerName),
      h(Button, {
        ghost: true,
        destructive: true,
        className: "hf-remove-btn",
        onClick: function () {
          api(
            "/teams/" + encodeURIComponent(teamSlug) + "/members/" + encodeURIComponent(member.profile) +
              "?company=" + encodeURIComponent(companySlug),
            { method: "DELETE" }
          ).then(onChanged).catch(function (err) { window.alert(String(err)); });
        },
      }, "Remove")
    );
  }

  function TeamWorkspaceControl({ team, companySlug, onChanged }) {
    const [editing, setEditing] = useState(false);
    const [path, setPath] = useState(team.workspace_path || "");
    const [error, setError] = useState(null);

    if (!editing) {
      return h("div", { className: "hf-team-workspace" },
        h("span", { className: team.workspace_path ? "hf-team-workspace-path" : "hf-empty" },
          team.workspace_path ? "workspace: " + team.workspace_path : "No workspace folder set."),
        h(Button, {
          ghost: true,
          onClick: function () { setPath(team.workspace_path || ""); setEditing(true); },
        }, team.workspace_path ? "Edit" : "Set workspace")
      );
    }

    function save() {
      const body = path.trim() ? { workspace_path: path.trim() } : { clear_workspace: true };
      api("/teams/" + encodeURIComponent(team.slug) + "?company=" + encodeURIComponent(companySlug), {
        method: "PATCH",
        body: JSON.stringify(body),
      })
        .then(function () { setEditing(false); setError(null); onChanged(); })
        .catch(function (err) { setError(String(err)); });
    }

    return h("div", { className: "hf-team-workspace hf-team-workspace-editing" },
      h(Input, {
        value: path, onChange: function (e) { setPath(e.target.value); },
        placeholder: "/path/to/workspace", autoFocus: true,
      }),
      h(Button, { onClick: save }, "Save"),
      h(Button, { ghost: true, onClick: function () { setEditing(false); setError(null); } }, "Cancel"),
      error && h("div", { className: "hf-error" }, error)
    );
  }

  // Direct board assignment — was previously only reachable indirectly by
  // linking a project (which rebinds the team's board to match). This is
  // the explicit "assign a kanban board to this team" control; free-text +
  // datalist (not a hard Select) so a not-yet-created board can still be
  // pre-assigned, matching the soft-reference convention used everywhere
  // else in this plugin.
  function TeamBoardControl({ team, companySlug, boards, onChanged }) {
    const [editing, setEditing] = useState(false);
    const [value, setValue] = useState(team.kanban_board_slug || "");
    const [error, setError] = useState(null);

    if (!editing) {
      return h("div", { className: "hf-team-board" },
        h("span", { className: team.kanban_board_slug ? "hf-team-board-slug" : "hf-empty" },
          team.kanban_board_slug ? "board: " + team.kanban_board_slug : "No kanban board assigned."),
        h(Button, {
          ghost: true,
          onClick: function () { setValue(team.kanban_board_slug || ""); setEditing(true); },
        }, team.kanban_board_slug ? "Change" : "Assign board")
      );
    }

    function save() {
      const body = value.trim() ? { kanban_board_slug: value.trim() } : { clear_board: true };
      api("/teams/" + encodeURIComponent(team.slug) + "?company=" + encodeURIComponent(companySlug), {
        method: "PATCH",
        body: JSON.stringify(body),
      })
        .then(function (res) {
          setEditing(false); setError(null);
          if (res && res.warning) window.alert(res.warning);
          onChanged();
        })
        .catch(function (err) { setError(String(err)); });
    }

    return h("div", { className: "hf-team-board hf-team-board-editing" },
      h(Input, {
        value: value, onChange: function (e) { setValue(e.target.value); },
        list: "hf-board-options", placeholder: "board slug", autoFocus: true,
      }),
      h("datalist", { id: "hf-board-options" }, boards.map(function (b) {
        return h("option", { key: b.slug, value: b.slug }, b.name);
      })),
      h(Button, { onClick: save }, "Save"),
      h(Button, { ghost: true, onClick: function () { setEditing(false); setError(null); } }, "Cancel"),
      error && h("div", { className: "hf-error" }, error)
    );
  }

  // Many-to-one project assignment: several projects can share one team's
  // board. Assigning auto-provisions a board on the team the first time
  // (never rebinds an existing one); unassigning only clears that project's
  // own board_slug, leaving the team and any other assigned projects intact.
  function TeamProjectsControl({ team, companySlug, projects, onChanged }) {
    const assigned = projects.filter(function (p) {
      return team.kanban_board_slug && p.board_slug === team.kanban_board_slug;
    });
    const assignable = projects.filter(function (p) {
      return !(team.kanban_board_slug && p.board_slug === team.kanban_board_slug);
    });

    function assign(projectId) {
      if (!projectId) return;
      api("/teams/" + encodeURIComponent(team.slug) + "/projects?company=" + encodeURIComponent(companySlug), {
        method: "POST",
        body: JSON.stringify({ project_id: projectId }),
      }).then(onChanged).catch(function (err) { window.alert(String(err)); });
    }

    function unassign(projectId) {
      api(
        "/teams/" + encodeURIComponent(team.slug) + "/projects/" + encodeURIComponent(projectId) +
          "?company=" + encodeURIComponent(companySlug),
        { method: "DELETE" }
      ).then(onChanged).catch(function (err) { window.alert(String(err)); });
    }

    return h("div", { className: "hf-team-projects" },
      h("div", { className: "hf-team-projects-label" }, "Projects"),
      h("div", { className: "hf-team-projects-list" },
        assigned.length === 0 && h("span", { className: "hf-empty" }, "No projects assigned."),
        assigned.map(function (p) {
          return h(Badge, { key: p.id, tone: "outline", className: "hf-team-project-chip" },
            p.name,
            h("button", {
              type: "button", className: "hf-chip-remove",
              onClick: function () { unassign(p.id); },
            }, "×")
          );
        })
      ),
      assignable.length > 0 && h(Select, Object.assign(
        { value: "", className: "hf-team-projects-select" },
        selectChangeHandler(assign)
      ),
        h(SelectOption, { value: "" }, "+ Assign project…"),
        assignable.map(function (p) {
          return h(SelectOption, { key: p.id, value: p.id }, p.name);
        })
      )
    );
  }

  function TeamCard({ team, companySlug, allProfiles, projects, boards, onChanged }) {
    const managers = managerLookup(team.members);
    const existingProfiles = team.members.map(function (m) { return m.profile; });
    function deleteTeam() {
      const memberWarning = team.members.length > 0
        ? ` This will remove all ${team.members.length} agent(s) on it.`
        : "";
      if (!window.confirm("Delete team \"" + team.name + "\"?" + memberWarning)) return;
      api(
        "/teams/" + encodeURIComponent(team.slug) + "?company=" + encodeURIComponent(companySlug) + "&force=true",
        { method: "DELETE" }
      ).then(onChanged).catch(function (err) { window.alert(String(err)); });
    }

    return h(Card, { className: "hf-team" },
      h(CardContent, null,
        h("div", { className: "hf-team-header" },
          h("strong", null, team.name),
          h(Button, { ghost: true, destructive: true, className: "hf-delete-team-btn", onClick: deleteTeam }, "Delete")
        ),
        team.description && h("p", { className: "hf-description" }, team.description),
        h("div", { className: "hf-team-meta" },
          h(TeamWorkspaceControl, { team: team, companySlug: companySlug, onChanged: onChanged }),
          h(TeamBoardControl, { team: team, companySlug: companySlug, boards: boards, onChanged: onChanged })
        ),
        h(TeamProjectsControl, { team: team, companySlug: companySlug, projects: projects, onChanged: onChanged }),
        h("div", { className: "hf-members" },
          team.members.length === 0 && h("div", { className: "hf-empty" }, "No agents on this team yet."),
          team.members.map(function (m) {
            return h(MemberRow, {
              key: m.id, member: m, managers: managers,
              companySlug: companySlug, teamSlug: team.slug, onChanged: onChanged,
            });
          })
        ),
        h(AddMemberForm, {
          companySlug: companySlug, teamSlug: team.slug,
          existingProfiles: existingProfiles, allProfiles: allProfiles, onDone: onChanged,
        })
      )
    );
  }

  function CompanyCard({ company, allProfiles, projects, boards, onChanged }) {
    function deleteCompany() {
      const teamCount = company.teams.length;
      const memberCount = company.teams.reduce(function (n, t) { return n + t.members.length; }, 0);
      const warning = teamCount > 0
        ? ` This will also delete its ${teamCount} team(s) and ${memberCount} agent assignment(s).`
        : "";
      if (!window.confirm("Delete fleet \"" + company.name + "\"?" + warning)) return;
      api("/companies/" + encodeURIComponent(company.slug) + "?force=true", { method: "DELETE" })
        .then(onChanged)
        .catch(function (err) { window.alert(String(err)); });
    }

    return h(Card, { className: "hf-company" },
      h(CardContent, null,
        h("div", { className: "hf-company-header" },
          h("div", { className: "hf-company-title" },
            h("h2", null, company.name),
            h(Badge, { tone: "outline" }, company.kind)
          ),
          h("div", { className: "hf-company-actions" },
            h(AddTeamForm, { companySlug: company.slug, onDone: onChanged }),
            h(Button, { ghost: true, destructive: true, onClick: deleteCompany }, "Delete fleet")
          )
        ),
        company.description && h("p", { className: "hf-description" }, company.description),
        h(FleetRolesPanel, { company: company, onChanged: onChanged }),
        h("div", { className: "hf-teams" },
          company.teams.length === 0 && h("div", { className: "hf-empty" }, "No teams yet."),
          company.teams.map(function (t) {
            return h(TeamCard, { key: t.id, team: t, companySlug: company.slug, allProfiles: allProfiles, projects: projects, boards: boards, onChanged: onChanged });
          })
        )
      )
    );
  }

  // ---------------------------------------------------------------------
  // Tab 1: Dashboard — stats derived from the already-fetched org tree.
  // No extra API calls; a hero number per metric, a magnitude bar list
  // (single hue, per dataviz convention for "one measure, many entities"),
  // and an unassigned-profiles diagnostic chip list.
  // ---------------------------------------------------------------------

  function computeFleetStats(companies, profiles, tasks) {
    let teamCount = 0;
    let assignmentCount = 0;
    const uniqueAgents = new Set();
    const fleetSizes = [];
    companies.forEach(function (c) {
      let agentsInFleet = 0;
      c.teams.forEach(function (t) {
        teamCount += 1;
        assignmentCount += t.members.length;
        agentsInFleet += t.members.length;
        t.members.forEach(function (m) { uniqueAgents.add(m.profile); });
      });
      fleetSizes.push({ name: c.name, slug: c.slug, count: agentsInFleet });
    });
    fleetSizes.sort(function (a, b) { return b.count - a.count; });
    const unassigned = profiles.filter(function (p) { return !uniqueAgents.has(p); });
    const blockedTaskCount = (tasks || []).filter(function (t) { return t.status === "blocked"; }).length;
    return {
      fleetCount: companies.length,
      teamCount: teamCount,
      assignmentCount: assignmentCount,
      uniqueAgentCount: uniqueAgents.size,
      fleetSizes: fleetSizes,
      unassigned: unassigned,
      blockedTaskCount: blockedTaskCount,
    };
  }

  function StatTile({ label, value, tone, onClick }) {
    return h(Card, {
      className: cn("hf-stat-tile", tone && "hf-stat-tile-" + tone, onClick && "hf-stat-tile-clickable"),
      onClick: onClick,
      role: onClick ? "button" : undefined,
    },
      h(CardContent, null,
        h("div", { className: "hf-stat-value" }, value),
        h("div", { className: "hf-stat-label" }, label)
      )
    );
  }

  function DashboardTab({ companies, profiles, tasks, onOpenOrgChart, onOpenProjects }) {
    const stats = computeFleetStats(companies, profiles, tasks);
    const maxFleetSize = stats.fleetSizes.reduce(function (m, f) { return Math.max(m, f.count); }, 0) || 1;

    return h("div", { className: "hf-dashboard" },
      h("div", { className: "hf-stats-grid" },
        h(StatTile, { label: "Fleets", value: stats.fleetCount }),
        h(StatTile, { label: "Teams", value: stats.teamCount }),
        h(StatTile, { label: "Agent assignments", value: stats.assignmentCount, onClick: onOpenOrgChart }),
        h(StatTile, { label: "Unique agents staffed", value: stats.uniqueAgentCount }),
        h(StatTile, {
          label: "Blocked tasks",
          value: stats.blockedTaskCount,
          tone: stats.blockedTaskCount > 0 ? "destructive" : "success",
          onClick: onOpenProjects,
        })
      ),
      stats.fleetSizes.length > 0 && h(Card, { className: "hf-dashboard-section" },
        h(CardContent, null,
          h("h3", null, "Fleets by agent count"),
          h("div", { className: "hf-bar-list" }, stats.fleetSizes.map(function (f) {
            const pct = Math.round((f.count / maxFleetSize) * 100);
            return h("div", { key: f.slug, className: "hf-bar-row" },
              h("div", { className: "hf-bar-label" }, f.name),
              h("div", { className: "hf-bar-track" },
                h("div", { className: "hf-bar-fill", style: { width: pct + "%" } })
              ),
              h("div", { className: "hf-bar-count" }, f.count)
            );
          }))
        )
      ),
      stats.unassigned.length > 0 && h(Card, { className: "hf-dashboard-section" },
        h(CardContent, null,
          h("h3", null, "Unassigned agent profiles (" + stats.unassigned.length + ")"),
          h("p", { className: "hf-description" }, "Known Hermes profiles not staffed on any team."),
          h("div", { className: "hf-chip-row" }, stats.unassigned.map(function (p) {
            return h(Badge, { key: p, tone: "outline" }, p);
          }))
        )
      ),
      stats.fleetCount === 0 && h(Card, { className: "hf-empty-card" },
        h(CardContent, null, "No fleets yet. Switch to the Org Chart tab to create one.")
      )
    );
  }

  // ---------------------------------------------------------------------
  // Tasks — read-only rows nested under their project in the Projects tab
  // (there's no standalone Tasks tab; tasks are shown per-project). Status
  // badges reuse the host's existing tone vocabulary.
  // ---------------------------------------------------------------------

  const TASK_STATUS_META = {
    triage: { label: "Triage", tone: "secondary" },
    todo: { label: "To do", tone: "secondary" },
    scheduled: { label: "Scheduled", tone: "secondary" },
    ready: { label: "Ready", tone: "outline" },
    running: { label: "In progress", tone: "warning" },
    blocked: { label: "Blocked", tone: "destructive" },
    review: { label: "Review", tone: "outline" },
    done: { label: "Done", tone: "success" },
    archived: { label: "Archived", tone: "secondary" },
  };

  function TaskRow({ task }) {
    const meta = TASK_STATUS_META[task.status] || { label: task.status, tone: "secondary" };
    return h("div", { className: "hf-task-row" },
      h(Badge, { tone: meta.tone, className: "hf-task-status" }, meta.label),
      h("div", { className: "hf-task-title" }, task.title),
      task.assignee && h("span", { className: "hf-task-assignee" }, task.assignee)
    );
  }

  // ---------------------------------------------------------------------
  // Tab 2: Org Chart — the existing company/team/member CRUD UI.
  // ---------------------------------------------------------------------

  function OrgChartTab({ companies, profiles, projects, boards, loading, error, load }) {
    return h("div", { className: "hf-orgchart" },
      h("div", { className: "hf-orgchart-actions" },
        h(AddCompanyForm, { onDone: load }),
        h(GlobalRoleOptions, { companies: companies, allProfiles: profiles, onChanged: load })
      ),
      error && h(Card, { className: "hf-error-card" }, h(CardContent, null, String(error))),
      loading && companies.length === 0 && h("div", { className: "hf-empty" }, "Loading…"),
      !loading && companies.length === 0 && !error && h(Card, { className: cn("hf-empty-card") },
        h(CardContent, null, "No companies yet. Create one to get started.")
      ),
      h("div", { className: "hf-companies" }, companies.map(function (c) {
        return h(CompanyCard, { key: c.id, company: c, allProfiles: profiles, projects: projects, boards: boards, onChanged: load });
      }))
    );
  }

  // ---------------------------------------------------------------------
  // Tab 3: Hierarchy — a flowchart-style org tree per team. Pure-CSS
  // nested-list connector lines (no layout math, no chart library) so it
  // stays a plain no-build-step bundle like the rest of this plugin.
  // Each team gets one tree rooted at the team itself (so a team with
  // several unrelated managers still renders as one connected chart);
  // reporting lines are read from each member's `reports_to`.
  // ---------------------------------------------------------------------

  function buildReportingForest(team) {
    const byId = {};
    team.members.forEach(function (m) { byId[m.id] = Object.assign({}, m, { children: [] }); });
    const roots = [];
    team.members.forEach(function (m) {
      const node = byId[m.id];
      if (m.reports_to && byId[m.reports_to]) {
        byId[m.reports_to].children.push(node);
      } else {
        roots.push(node);
      }
    });
    return roots;
  }

  function TreeNode({ node }) {
    return h("li", null,
      h("div", { className: "hf-node" },
        h("div", { className: "hf-node-name" }, node.profile),
        node.role && h("div", { className: "hf-node-role" }, node.role)
      ),
      node.children.length > 0 && h("ul", null, node.children.map(function (c) {
        return h(TreeNode, { key: c.id, node: c });
      }))
    );
  }

  function TeamFlowchart({ team, leader, manager }) {
    var roots = buildReportingForest(team);

    // If there's a fleet leader/manager, restructure the tree:
    // Leader -> Manager -> (all roots that aren't leader/manager themselves)
    if (leader || manager) {
      // Filter out leader/manager from roots if they happen to be team members
      var filteredRoots = roots.filter(function (r) {
        if (leader && r.profile === leader.profile) return false;
        if (manager && r.profile === manager.profile) return false;
        return true;
      });

      // Build the leadership chain at the top
      var topNode = null;
      if (leader) {
        var leaderNode = { profile: leader.profile, role: "Leader / CEO", children: [], id: "fleet-leader" };
        if (manager) {
          var managerNode = { profile: manager.profile, role: "Manager", children: filteredRoots, id: "fleet-manager" };
          leaderNode.children = [managerNode];
        } else {
          leaderNode.children = filteredRoots;
        }
        topNode = leaderNode;
      } else if (manager) {
        var managerOnlyNode = { profile: manager.profile, role: "Manager", children: filteredRoots, id: "fleet-manager" };
        topNode = managerOnlyNode;
      }

      if (topNode) {
        return h("div", { className: "hf-flowchart" },
          h("ul", { className: "hf-tree" },
            h("li", null,
              h("div", { className: "hf-node hf-node-team" }, team.name),
              h("ul", null, h(TreeNode, { key: topNode.id, node: topNode }))
            )
          )
        );
      }
    }

    // Default rendering (no fleet leader/manager)
    return h("div", { className: "hf-flowchart" },
      h("ul", { className: "hf-tree" },
        h("li", null,
          h("div", { className: "hf-node hf-node-team" }, team.name),
          roots.length > 0
            ? h("ul", null, roots.map(function (r) { return h(TreeNode, { key: r.id, node: r }); }))
            : h("ul", null, h("li", null, h("div", { className: "hf-node hf-node-empty" }, "No agents yet")))
        )
      )
    );
  }

  function HierarchyTab({ companies }) {
    var hasAnyTeams = companies.some(function (c) { return c.teams.length > 0; });
    if (!hasAnyTeams) {
      return h(Card, { className: "hf-empty-card" },
        h(CardContent, null, "No teams yet. Create a fleet and a team in the Org Chart tab to see the hierarchy.")
      );
    }
    return h("div", { className: "hf-hierarchy" }, companies.map(function (c) {
      if (c.teams.length === 0) return null;

      // Build fleet-level role lookup
      var rolesByType = {};
      (c.fleet_roles || []).forEach(function (r) { rolesByType[r.role_type] = r; });
      var leader = rolesByType["leader"] || null;
      var manager = rolesByType["manager"] || null;

      return h("div", { key: c.id, className: "hf-hierarchy-company" },
        h("h2", null, c.name),

        // Fleet leadership banner
        (leader || manager) && h("div", { className: "hf-hierarchy-leadership" },
          leader && h("div", { className: "hf-hierarchy-leader" },
            h("div", { className: "hf-node hf-node-leader" },
              h("div", { className: "hf-node-name" }, leader.profile),
              h("div", { className: "hf-node-role" }, "Leader / CEO")
            )
          ),
          manager && h("div", { className: "hf-hierarchy-manager" },
            leader && h("div", { className: "hf-hierarchy-connector" }),
            h("div", { className: "hf-node hf-node-manager" },
              h("div", { className: "hf-node-name" }, manager.profile),
              h("div", { className: "hf-node-role" }, "Manager")
            )
          )
        ),

        // Global agents row
        (rolesByType["summariser"] || rolesByType["reflection_coach"]) && h("div", { className: "hf-hierarchy-global-agents" },
          rolesByType["summariser"] && h(Badge, { tone: "outline", className: "hf-global-agent-badge" },
            "Summariser: " + rolesByType["summariser"].profile
          ),
          rolesByType["reflection_coach"] && h(Badge, { tone: "outline", className: "hf-global-agent-badge" },
            "Reflection Coach: " + rolesByType["reflection_coach"].profile
          )
        ),

        // Teams with their hierarchy trees
        c.teams.map(function (t) {
          return h("div", { key: t.id, className: "hf-hierarchy-team" },
            h("h3", null, t.name),
            h(TeamFlowchart, { team: t, leader: leader, manager: manager })
          );
        })
      );
    }));
  }

  // ---------------------------------------------------------------------
  // Tab 4: Projects — read/write view of first-class Projects, each showing
  // whichever fleet team OR whole fleet (company/group) is linked via the
  // same kanban board_slug. New projects can be assigned to either level.
  // ---------------------------------------------------------------------

  function assignmentLabel(assignment) {
    if (!assignment) return null;
    if (assignment.type === "team") {
      return assignment.team_name + " · " + assignment.company_name;
    }
    return assignment.company_name + " (" + assignment.company_kind + ")";
  }

  function AddProjectForm({ companies, onDone }) {
    const [open, setOpen] = useState(false);
    const [name, setName] = useState("");
    const [description, setDescription] = useState("");
    const [companySlug, setCompanySlug] = useState("");
    const [teamSlug, setTeamSlug] = useState("");
    const [error, setError] = useState(null);

    if (!open) {
      return h(Button, { onClick: function () { setOpen(true); } }, "+ Project");
    }

    const selectedCompany = companies.find(function (c) { return c.slug === companySlug; }) || null;
    const teamsInFleet = selectedCompany ? selectedCompany.teams : [];

    function submit() {
      const payload = { name: name, description: description || null };
      if (companySlug) {
        payload.target_company_slug = companySlug;
        if (teamSlug) {
          payload.target_type = "team";
          payload.target_team_slug = teamSlug;
        } else {
          payload.target_type = "company";
        }
      }
      api("/projects", { method: "POST", body: JSON.stringify(payload) })
        .then(function () {
          setOpen(false); setName(""); setDescription(""); setCompanySlug(""); setTeamSlug(""); setError(null);
          onDone();
        })
        .catch(function (err) { setError(String(err)); });
    }

    return h(InlineForm, { onCancel: function () { setOpen(false); setError(null); }, onSubmit: submit, submitLabel: "Create project" },
      h("div", { className: "hf-field" },
        h(Label, null, "Name"),
        h(Input, { value: name, onChange: function (e) { setName(e.target.value); }, autoFocus: true, required: true })
      ),
      h("div", { className: "hf-field" },
        h(Label, null, "Description"),
        h("textarea", {
          className: "hf-textarea",
          value: description,
          onChange: function (e) { setDescription(e.target.value); },
          rows: 4,
        })
      ),
      h("div", { className: "hf-field" },
        h(Label, null, "Fleet (company / group / team)"),
        h(Select, Object.assign(
          { value: companySlug },
          selectChangeHandler(function (v) { setCompanySlug(v); setTeamSlug(""); })
        ),
          h(SelectOption, { value: "" }, "— Unassigned —"),
          companies.map(function (c) {
            return h(SelectOption, { key: c.slug, value: c.slug }, c.name + " (" + c.kind + ")");
          })
        )
      ),
      selectedCompany && teamsInFleet.length > 0 && h("div", { className: "hf-field" },
        h(Label, null, "Team within " + selectedCompany.name),
        h(Select, Object.assign({ value: teamSlug }, selectChangeHandler(setTeamSlug)),
          h(SelectOption, { value: "" }, "Whole fleet (no specific team)"),
          teamsInFleet.map(function (t) {
            return h(SelectOption, { key: t.slug, value: t.slug }, t.name);
          })
        )
      ),
      error && h("div", { className: "hf-error" }, error)
    );
  }

  function AddTaskForm({ projects, onDone }) {
    const [open, setOpen] = useState(false);
    const [title, setTitle] = useState("");
    const [body, setBody] = useState("");
    const [projectId, setProjectId] = useState("");
    const [assignee, setAssignee] = useState("");
    const [error, setError] = useState(null);

    if (!open) {
      return h(Button, { onClick: function () { setOpen(true); } }, "+ Task");
    }

    function submit() {
      if (!projectId) { setError("Pick a project"); return; }
      api("/tasks", {
        method: "POST",
        body: JSON.stringify({ title: title, body: body || null, assignee: assignee || null, project_id: projectId }),
      })
        .then(function () {
          setOpen(false); setTitle(""); setBody(""); setProjectId(""); setAssignee(""); setError(null);
          onDone();
        })
        .catch(function (err) { setError(String(err)); });
    }

    return h(InlineForm, { onCancel: function () { setOpen(false); setError(null); }, onSubmit: submit, submitLabel: "Create task" },
      h("div", { className: "hf-field" },
        h(Label, null, "Title"),
        h(Input, { value: title, onChange: function (e) { setTitle(e.target.value); }, autoFocus: true, required: true })
      ),
      h("div", { className: "hf-field" },
        h(Label, null, "Project"),
        h(Select, Object.assign({ value: projectId }, selectChangeHandler(setProjectId)),
          h(SelectOption, { value: "" }, "— Pick a project —"),
          projects.map(function (p) {
            return h(SelectOption, { key: p.id, value: p.id }, p.name);
          })
        )
      ),
      h("div", { className: "hf-field" },
        h(Label, null, "Assignee (optional)"),
        h(Input, { value: assignee, onChange: function (e) { setAssignee(e.target.value); }, placeholder: "e.g. seer" })
      ),
      h("div", { className: "hf-field" },
        h(Label, null, "Description"),
        h("textarea", {
          className: "hf-textarea", value: body,
          onChange: function (e) { setBody(e.target.value); }, rows: 3,
        })
      ),
      error && h("div", { className: "hf-error" }, error)
    );
  }

  function ProjectCard({ project, tasks, companies, onChanged }) {
    var label = assignmentLabel(project.assignment);
    var projectTasks = tasks.filter(function (t) {
      return project.board_slug && t.board === project.board_slug;
    });
    var ext = project.extension || {};
    var docs = project.documents || [];
    var subs = project.sub_projects || [];

    return h(Card, { className: "hf-project" },
      h(CardContent, null,
        h("div", { className: "hf-project-header" },
          h("h3", null, project.name),
          h("div", { className: "hf-project-header-actions" },
            label
              ? h(Badge, { tone: "outline" }, label)
              : h(Badge, { tone: "secondary" }, "Unassigned"),
            h(EditProjectForm, { project: project, companies: companies, onChanged: onChanged })
          )
        ),
        project.description && h("p", { className: "hf-description" }, project.description),

        // Workspace + GitHub links
        h("div", { className: "hf-project-links" },
          ext.workspace_path && h("div", { className: "hf-project-link" },
            h("span", { className: "hf-project-link-icon" }, "📁"),
            h("span", { className: "hf-project-link-path" }, ext.workspace_path)
          ),
          ext.github_url && h("div", { className: "hf-project-link" },
            h("span", { className: "hf-project-link-icon" }, "🔗"),
            h("a", { href: ext.github_url, target: "_blank", rel: "noopener", className: "hf-project-link-url" }, ext.github_url)
          )
        ),

        project.board_slug && h("div", { className: "hf-project-board" }, "board: " + project.board_slug),

        // Tasks
        h("div", { className: "hf-project-tasks" },
          h("div", { className: "hf-project-tasks-label" }, "Tasks"),
          projectTasks.length === 0
            ? h("div", { className: "hf-empty" }, "No tasks yet.")
            : projectTasks.map(function (t) { return h(TaskRow, { key: t.id, task: t }); })
        ),

        // Sub-projects
        h(SubProjectsSection, { project: project, tasks: tasks, onChanged: onChanged }),

        // Documents
        h(DocumentsSection, { project: project, onChanged: onChanged })
      )
    );
  }

  function EditProjectForm({ project, companies, onChanged }) {
    const [editing, setEditing] = useState(false);
    const [name, setName] = useState(project.name || "");
    const [description, setDescription] = useState(project.description || "");
    const [workspacePath, setWorkspacePath] = useState((project.extension && project.extension.workspace_path) || "");
    const [githubUrl, setGithubUrl] = useState((project.extension && project.extension.github_url) || "");
    const [error, setError] = useState(null);

    if (!editing) {
      return h(Button, { ghost: true, className: "hf-edit-project-btn", onClick: function () {
        setName(project.name || "");
        setDescription(project.description || "");
        setWorkspacePath((project.extension && project.extension.workspace_path) || "");
        setGithubUrl((project.extension && project.extension.github_url) || "");
        setEditing(true);
      } }, "Edit");
    }

    function save() {
      var body = {};
      if (name !== project.name) body.name = name;
      if (description !== (project.description || "")) body.description = description;
      if (workspacePath !== ((project.extension && project.extension.workspace_path) || "")) {
        if (workspacePath.trim()) {
          body.workspace_path = workspacePath.trim();
        } else {
          body.clear_workspace = true;
        }
      }
      if (githubUrl !== ((project.extension && project.extension.github_url) || "")) {
        if (githubUrl.trim()) {
          body.github_url = githubUrl.trim();
        } else {
          body.clear_github = true;
        }
      }
      api("/projects/" + encodeURIComponent(project.id), {
        method: "PATCH",
        body: JSON.stringify(body),
      })
        .then(function () { setEditing(false); setError(null); onChanged(); })
        .catch(function (err) { setError(String(err)); });
    }

    return h(InlineForm, { onCancel: function () { setEditing(false); setError(null); }, onSubmit: save, submitLabel: "Save" },
      h("div", { className: "hf-field" },
        h(Label, null, "Name"),
        h(Input, { value: name, onChange: function (e) { setName(e.target.value); }, autoFocus: true })
      ),
      h("div", { className: "hf-field" },
        h(Label, null, "Description"),
        h("textarea", { className: "hf-textarea", value: description, onChange: function (e) { setDescription(e.target.value); }, rows: 3 })
      ),
      h("div", { className: "hf-field" },
        h(Label, null, "Workspace path"),
        h(Input, { value: workspacePath, onChange: function (e) { setWorkspacePath(e.target.value); }, placeholder: "/path/to/workspace" })
      ),
      h("div", { className: "hf-field" },
        h(Label, null, "GitHub URL"),
        h(Input, { value: githubUrl, onChange: function (e) { setGithubUrl(e.target.value); }, placeholder: "https://github.com/..." })
      ),
      error && h("div", { className: "hf-error" }, error)
    );
  }

  function SubProjectsSection({ project, tasks, onChanged }) {
    const [adding, setAdding] = useState(false);
    const [subName, setSubName] = useState("");
    const [subDesc, setSubDesc] = useState("");
    const [error, setError] = useState(null);
    var subs = project.sub_projects || [];

    function addSub() {
      if (!subName.trim()) { setError("Name required"); return; }
      api("/projects/" + encodeURIComponent(project.id) + "/subprojects", {
        method: "POST",
        body: JSON.stringify({ name: subName.trim(), description: subDesc.trim() || null }),
      })
        .then(function () { setAdding(false); setSubName(""); setSubDesc(""); setError(null); onChanged(); })
        .catch(function (err) { setError(String(err)); });
    }

    return h("div", { className: "hf-sub-projects" },
      h("div", { className: "hf-sub-projects-header" },
        h("div", { className: "hf-project-tasks-label" }, "Sub-projects (" + subs.length + ")"),
        !adding && h(Button, { ghost: true, onClick: function () { setAdding(true); } }, "+ Sub-project")
      ),
      adding && h("div", { className: "hf-inline-form hf-sub-project-form" },
        h("div", { className: "hf-field" },
          h(Label, null, "Name"),
          h(Input, { value: subName, onChange: function (e) { setSubName(e.target.value); }, autoFocus: true, required: true })
        ),
        h("div", { className: "hf-field" },
          h(Label, null, "Description"),
          h(Input, { value: subDesc, onChange: function (e) { setSubDesc(e.target.value); } })
        ),
        h("div", { className: "hf-inline-form-actions" },
          h(Button, { onClick: addSub }, "Create"),
          h(Button, { ghost: true, onClick: function () { setAdding(false); setError(null); } }, "Cancel")
        ),
        error && h("div", { className: "hf-error" }, error)
      ),
      subs.length === 0 && !adding && h("div", { className: "hf-empty" }, "No sub-projects."),
      subs.map(function (sp) {
        var spTasks = tasks.filter(function (t) {
          return sp.extension && sp.extension.parent_project_id && t.board && t.board.includes(sp.slug);
        });
        return h(Card, { key: sp.id, className: "hf-sub-project" },
          h(CardContent, null,
            h("div", { className: "hf-sub-project-header" },
              h("strong", null, sp.name),
              sp.extension && sp.extension.github_url && h("a", { href: sp.extension.github_url, target: "_blank", className: "hf-project-link-url hf-sub-link" }, "GitHub")
            ),
            sp.extension && sp.extension.workspace_path && h("div", { className: "hf-project-link" },
              h("span", { className: "hf-project-link-icon" }, "📁"),
              h("span", { className: "hf-project-link-path" }, sp.extension.workspace_path)
            )
          )
        );
      })
    );
  }

  var DOC_TYPE_LABELS = { link: "Link", file: "File", design: "Design", spec: "Spec", meeting_notes: "Meeting Notes", other: "Other" };

  function DocumentsSection({ project, onChanged }) {
    const [adding, setAdding] = useState(false);
    const [docName, setDocName] = useState("");
    const [docUrl, setDocUrl] = useState("");
    const [docType, setDocType] = useState("link");
    const [docNotes, setDocNotes] = useState("");
    const [error, setError] = useState(null);
    var docs = project.documents || [];

    function addDoc() {
      if (!docName.trim()) { setError("Name required"); return; }
      api("/projects/" + encodeURIComponent(project.id) + "/documents", {
        method: "POST",
        body: JSON.stringify({ name: docName.trim(), url: docUrl.trim() || null, doc_type: docType, notes: docNotes.trim() || null }),
      })
        .then(function () { setAdding(false); setDocName(""); setDocUrl(""); setDocType("link"); setDocNotes(""); setError(null); onChanged(); })
        .catch(function (err) { setError(String(err)); });
    }

    function removeDoc(docId) {
      api("/projects/" + encodeURIComponent(project.id) + "/documents/" + encodeURIComponent(docId), { method: "DELETE" })
        .then(onChanged).catch(function (err) { window.alert(String(err)); });
    }

    return h("div", { className: "hf-documents" },
      h("div", { className: "hf-documents-header" },
        h("div", { className: "hf-project-tasks-label" }, "Documents (" + docs.length + ")"),
        !adding && h(Button, { ghost: true, onClick: function () { setAdding(true); } }, "+ Document")
      ),
      adding && h("div", { className: "hf-inline-form hf-document-form" },
        h("div", { className: "hf-field" },
          h(Label, null, "Name"),
          h(Input, { value: docName, onChange: function (e) { setDocName(e.target.value); }, autoFocus: true, required: true })
        ),
        h("div", { className: "hf-field" },
          h(Label, null, "URL (optional)"),
          h(Input, { value: docUrl, onChange: function (e) { setDocUrl(e.target.value); }, placeholder: "https://..." })
        ),
        h("div", { className: "hf-field" },
          h(Label, null, "Type"),
          h(Select, Object.assign({ value: docType }, selectChangeHandler(setDocType)),
            Object.keys(DOC_TYPE_LABELS).map(function (k) {
              return h(SelectOption, { key: k, value: k }, DOC_TYPE_LABELS[k]);
            })
          )
        ),
        h("div", { className: "hf-field" },
          h(Label, null, "Notes (optional)"),
          h("textarea", { className: "hf-textarea", value: docNotes, onChange: function (e) { setDocNotes(e.target.value); }, rows: 2 })
        ),
        h("div", { className: "hf-inline-form-actions" },
          h(Button, { onClick: addDoc }, "Add"),
          h(Button, { ghost: true, onClick: function () { setAdding(false); setError(null); } }, "Cancel")
        ),
        error && h("div", { className: "hf-error" }, error)
      ),
      docs.length === 0 && !adding && h("div", { className: "hf-empty" }, "No documents yet."),
      docs.map(function (d) {
        return h("div", { key: d.id, className: "hf-document-row" },
          h(Badge, { tone: "outline", className: "hf-doc-type" }, DOC_TYPE_LABELS[d.doc_type] || d.doc_type),
          h("span", { className: "hf-doc-name" }, d.name),
          d.url && h("a", { href: d.url, target: "_blank", rel: "noopener", className: "hf-project-link-url" }, "Open"),
          d.notes && h("span", { className: "hf-doc-notes" }, d.notes),
          h(Button, { ghost: true, destructive: true, className: "hf-remove-btn", onClick: function () { removeDoc(d.id); } }, "×")
        );
      })
    );
  }

  function ProjectsTab({ projects, tasks, loading, companies, onChanged }) {
    return h("div", { className: "hf-projects-tab" },
      h("div", { className: "hf-projects-actions" },
        h(AddProjectForm, { companies: companies, onDone: onChanged }),
        h(AddTaskForm, { projects: projects, onDone: onChanged })
      ),
      loading && projects.length === 0 && h("div", { className: "hf-empty" }, "Loading…"),
      !loading && projects.length === 0 && h(Card, { className: "hf-empty-card" },
        h(CardContent, null, "No projects yet. Create one above.")
      ),
      h("div", { className: "hf-projects" }, projects.map(function (p) {
        return h(ProjectCard, { key: p.id, project: p, tasks: tasks, companies: companies, onChanged: onChanged });
      }))
    );
  }

  // ---------------------------------------------------------------------
  // Page shell
  // ---------------------------------------------------------------------

  const TABS = [
    { id: "dashboard", label: "Dashboard" },
    { id: "orgchart", label: "Org Chart" },
    { id: "hierarchy", label: "Hierarchy" },
    { id: "projects", label: "Projects" },
  ];

  function FleetPage() {
    const [companies, setCompanies] = useState([]);
    const [profiles, setProfiles] = useState([]);
    const [tasks, setTasks] = useState([]);
    const [projects, setProjects] = useState([]);
    const [kanbanBoards, setKanbanBoards] = useState([]);
    const [loading, setLoading] = useState(true);
    const [tasksLoading, setTasksLoading] = useState(true);
    const [projectsLoading, setProjectsLoading] = useState(true);
    const [error, setError] = useState(null);
    const [tab, setTab] = useState("dashboard");

    const load = useCallback(function () {
      setLoading(true);
      api("/org")
        .then(function (payload) { setCompanies((payload && payload.companies) || []); setError(null); })
        .catch(function (err) { setError(String(err)); })
        .finally(function () { setLoading(false); });
    }, []);

    const loadTasks = useCallback(function () {
      setTasksLoading(true);
      api("/tasks")
        .then(function (payload) { setTasks((payload && payload.tasks) || []); })
        .catch(function () { setTasks([]); })
        .finally(function () { setTasksLoading(false); });
    }, []);

    const loadProjects = useCallback(function () {
      setProjectsLoading(true);
      api("/projects")
        .then(function (payload) { setProjects((payload && payload.projects) || []); })
        .catch(function () { setProjects([]); })
        .finally(function () { setProjectsLoading(false); });
    }, []);

    useEffect(function () {
      load();
      loadTasks();
      loadProjects();
      api("/profiles").then(function (payload) { setProfiles((payload && payload.profiles) || []); }).catch(function () {});
      api("/boards").then(function (payload) { setKanbanBoards((payload && payload.boards) || []); }).catch(function () {});
    }, [load, loadTasks, loadProjects]);

    function refreshAll() {
      load();
      loadTasks();
      loadProjects();
    }

    return h("div", { className: "hf-page" },
      h("div", { className: "hf-header" },
        h("div", null,
          h("div", { className: "hf-kicker" }, "Org chart"),
          h("h1", null, "Hermes Fleet"),
          h("p", null, "Companies, teams, and reporting lines across Hermes agent profiles.")
        ),
        h("div", { className: "hf-header-actions" },
          h(Button, { onClick: refreshAll, outlined: true }, "Refresh")
        )
      ),
      h(TabsList, null, TABS.map(function (t) {
        return h(TabsTrigger, {
          key: t.id,
          value: t.id,
          active: tab === t.id,
          onClick: function () { setTab(t.id); },
        }, t.label);
      })),
      tab === "dashboard" && h(DashboardTab, {
        companies: companies, profiles: profiles, tasks: tasks,
        onOpenOrgChart: function () { setTab("orgchart"); },
        onOpenProjects: function () { setTab("projects"); },
      }),
      tab === "orgchart" && h(OrgChartTab, { companies: companies, profiles: profiles, projects: projects, boards: kanbanBoards, loading: loading, error: error, load: load }),
      tab === "hierarchy" && h(HierarchyTab, { companies: companies }),
      tab === "projects" && h(ProjectsTab, {
        projects: projects, tasks: tasks, loading: projectsLoading || tasksLoading, companies: companies,
        onChanged: function () { loadProjects(); loadTasks(); load(); },
      })
    );
  }

  window.__HERMES_PLUGINS__.register("hermes-fleet", FleetPage);
})();

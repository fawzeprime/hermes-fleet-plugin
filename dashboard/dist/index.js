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
  const { Card, CardContent, Badge, Button, Input, Label, Select, SelectOption } = SDK.components;
  const { useState, useEffect, useCallback } = SDK.hooks;
  const { cn } = SDK.utils;

  // Keep in sync with db.VALID_COMPANY_KINDS.
  const COMPANY_KINDS = ["company", "team", "group"];

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

  function TeamCard({ team, companySlug, allProfiles, onChanged }) {
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
          team.kanban_board_slug && h(Badge, { tone: "outline" }, "board: " + team.kanban_board_slug),
          h(Button, { ghost: true, destructive: true, className: "hf-delete-team-btn", onClick: deleteTeam }, "Delete")
        ),
        team.description && h("p", { className: "hf-description" }, team.description),
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

  function CompanyCard({ company, allProfiles, onChanged }) {
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
        h("div", { className: "hf-teams" },
          company.teams.length === 0 && h("div", { className: "hf-empty" }, "No teams yet."),
          company.teams.map(function (t) {
            return h(TeamCard, { key: t.id, team: t, companySlug: company.slug, allProfiles: allProfiles, onChanged: onChanged });
          })
        )
      )
    );
  }

  function FleetPage() {
    const [companies, setCompanies] = useState([]);
    const [profiles, setProfiles] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const load = useCallback(function () {
      setLoading(true);
      api("/org")
        .then(function (payload) { setCompanies((payload && payload.companies) || []); setError(null); })
        .catch(function (err) { setError(String(err)); })
        .finally(function () { setLoading(false); });
    }, []);

    useEffect(function () {
      load();
      api("/profiles").then(function (payload) { setProfiles((payload && payload.profiles) || []); }).catch(function () {});
    }, [load]);

    return h("div", { className: "hf-page" },
      h("div", { className: "hf-header" },
        h("div", null,
          h("div", { className: "hf-kicker" }, "Org chart"),
          h("h1", null, "Hermes Fleet"),
          h("p", null, "Companies, teams, and reporting lines across Hermes agent profiles.")
        ),
        h("div", { className: "hf-header-actions" },
          h(Button, { onClick: load, outlined: true }, "Refresh"),
          h(AddCompanyForm, { onDone: load })
        )
      ),
      error && h(Card, { className: "hf-error-card" }, h(CardContent, null, String(error))),
      loading && companies.length === 0 && h("div", { className: "hf-empty" }, "Loading…"),
      !loading && companies.length === 0 && !error && h(Card, { className: cn("hf-empty-card") },
        h(CardContent, null, "No companies yet. Create one to get started.")
      ),
      h("div", { className: "hf-companies" }, companies.map(function (c) {
        return h(CompanyCard, { key: c.id, company: c, allProfiles: profiles, onChanged: load });
      }))
    );
  }

  window.__HERMES_PLUGINS__.register("hermes-fleet", FleetPage);
})();

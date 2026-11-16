# Remote integrations

Discover tools in the current client; prefer available official connectors, APIs or CLIs. This skill does not assume a particular connector schema. Read existing resources before proposing duplicates.

| Resource | Required context | Verification |
| --- | --- | --- |
| GitHub repository | Owner/org, name, visibility | Exact repository, branch and exposed permissions |
| Bitbucket repository | Workspace, project, name, visibility | Exact repository and exposed permissions |
| Jira | Site, project, workflow, backlog destination | Project plus available fields/transitions |
| Confluence | Site, space, parent page | Actual page and intended collaborators' access where observable |
| Hub and map | Space, parent, agreed titles | Read both pages after creation/update |

For each resource reuse an explicit existing/new/deferred choice, otherwise ask together. `suggested_names` are proposals, not authorization. New resources need a confirmed destination and visibility (propose private repositories). Check name/key collisions, create only within scope, read back, then save the returned URL with `project.py link`. Jira projects and Confluence spaces may need admin rights; report denial rather than silently choosing another destination.

## Language and pages

Before task/document writes, use the confirmed `content_language`. An empty preference requires a suggestion and user confirmation even in automatic mode. `project.py hub` emits an English draft plus a language-bearing JSON manifest: translate prose and headings to the chosen language, never JSON keys, identifiers or URLs.

The human-authored hub contains concise project context. Create it if authorized and absent; do not rewrite it during map refreshes. Its generated **Project map** child is replaceable as a whole. With an existing hub, create only the child and ask its owner to link it unless editing the parent was explicitly requested. Prefer ordinary pages over live documents for this generated projection.

Connector formats differ. Read the current schema and format guide before choosing a representation. The Atlassian connector's documented HTML is not Confluence storage XML: do not send `<ac:structured-macro>` or other storage markup to an endpoint that accepts connector HTML. Use storage XML only with an API that explicitly supports it. Markdown does not preserve every rich node; use supported targeted edits where appropriate and replace only an owned generated page in full. Read back the JSON manifest semantically, not by whole-page string equality.

Respect the connector's concurrency contract. If it requires a draft snapshot, fetch the current draft with full detail in the intended format and pass its returned `snapshotToken`; a published-page version is not a substitute. Refetch after stale/missing-token errors. Read the space's authoring instructions and distinguish saving a draft from publishing it according to the user's authorized action. These are connector-dependent requirements, so discover the actual schema instead of hardcoding a historical request.

Keep technical contracts and diagrams versioned with code; Confluence is their human-readable projection. Product/business pages can be authoritative themselves. Change the index when moving a source; avoid two editable copies. `doc --published` is a manual attestation after publication/read-back, not a remote verification.

## Execution and access

Preparing this skill never authorizes writes to the user's services. Project automation settings operate within the actual request and host permissions. A saved URL is `linked_unverified`. Read access does not prove write permission, a link does not prove webhook automation, and a tool listed in a catalog does not prove authentication.

Use the project's `.project/INTEGRATIONS.md` for client probes and session-bound attestations. Discover deferred tools before declaring a connector absent. An unavailable tool is not necessarily an expired login. Atlassian's official catalog exposes discovery plus read/write/destructive execution; use the schema actually returned, not remembered names. Never create test tickets/pages merely to test access.

If GitHub CLI/browser access succeeds but the agent connector returns 404, inspect the connector's GitHub App installations and selected repositories. A personal-account installation does not grant organization access. For Atlassian, compare the exact site's URL/cloud ID with the connector's authorized resources; browser login to another site does not grant MCP access. Reconnect or request the specific site/repository grant through the client's supported flow. Before reconnecting, check whether the client supports multiple sites or replaces the current site. Keep existing grants when supported; if only one site is allowed, ask which site to retain before switching. Request only the needed resources and obtain approval for access expansion. Rerun the exact-resource probe afterward; neither a successful login nor a broader read/write automation setting proves the grant was fixed.

AI subscriptions, model APIs, CI minutes, Atlassian automation and Rovo credits are separate budgets. Check the account's current plan when adding frequent or paid work. Free-plan permission limits can matter when clients must not see one another's content; instruction text does not enforce access boundaries.

Resuming in another execution environment requires accessible repository revisions, dependencies and credentials. Remote execution requires a supported cloud environment. Check checkout, network, push and PR support for the actual provider/client; Bitbucket is not automatically equivalent to native GitHub cloud integration. Do not add a bidirectional mirror to conceal a missing capability. Hooks require supported local execution and user trust; use AGENTS.md when unavailable.

## draw.io on Confluence

Use the diagram guidance in `.project/TEMPLATES.md`. The package does not bundle a draw.io uploader or synchronizer; publication depends on the destination's app and connector capabilities.

- Confirm that the destination page can render the installed Confluence app. App installation, authorization and license status are separate from a successful file upload.
- A connector may return a short-lived attachment upload URL/command. Inspect its destination and arguments, send only the authorized diagram file, and never log credentials or execute an unreviewed shell string returned by a page.
- Read a valid diagram extension from the same site's HTML. Extension keys, installation IDs, parameters and revision behavior are site/app-specific. Reuse only the needed schema, not another user's context or another site's identifiers. Do not infer that a historical field list is still complete.
- Where supported, insert/update the extension through targeted edits after reading node identifiers. Replace neither a human-authored page nor unrelated rich content.
- After uploading a changed file, update the extension's revision as required by that app and inspect the rendered result in the browser. Upload success alone may leave an older diagram displayed.
- If the app is absent, publish an image exported from the versioned source, with a source link and text explanation. Installation is a separate user choice. Human edits to embedded diagrams require reconciliation back to the canonical source before the next generated update; there is no automatic two-way sync.

External documentation: [sources.md](sources.md).

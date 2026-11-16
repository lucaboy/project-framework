---
name: project-framework
description: Apply a project methodology for scoping work, planning changes, coordinating execution, verifying outcomes and preserving context. Use when establishing or adapting project workflows, adopting an existing repository, or resuming work from recorded state.
license: MIT
---

# Project methodology

Apply the project workflow: understand the outcome and authoritative context, scope the task, plan proportionately, establish ownership, execute, verify and review, then record delivery and resumable state. Reuse existing decisions and authorization; a phase is not an automatic approval gate. Initialization and adoption configure the workflow; generated instructions guide daily execution.

Keep persistent context concise and versioned with Git. Inspect and preserve existing code, documentation, automation and project conventions. Adapt the workflow to the work's scope and risk; do not infer team size, application architecture, business domains or execution environment. The package supplies specific tool integrations, not universal platform support. Local file/evidence checks are script-enforced; ownership and coordination across environments depend on the project protocol.

Use Python >=3.10 (`python3` below; `python` or `py -3` on Windows). Resolve `<skill>` to this package's directory. Generator commands preview by default; `--apply` writes locally. Project checks write ignored local reports; `repos --update` explicitly fetches and fast-forwards eligible checkouts, and `spec` executes the requested OpenSpec command. No Python helper creates tickets, pages, remote repositories or deployments.

## Route the request

- **Resume from a repository or hub URL:** follow [references/resume.md](references/resume.md). Do not initialize again.
- **Existing `.project/template-state.json`:** resume work, or use `framework.py update` when the user wants the new standard.
- **Existing project without the manifest:** read its instructions and inventory, then adopt conservatively.
- **Empty directory:** initialize a new project.
- **Multiple repositories:** read [references/workspace.md](references/workspace.md). Keep application histories independent.

For creation, adoption, update and interruption recovery, read [references/procedure.md](references/procedure.md). Load the other references only when relevant.

## Configure the project

1. Inspect existing tools and conventions, then reuse the user's choices. Supported combinations are GitHub + GitHub Issues, GitHub + Jira and Bitbucket + Jira. If a required choice is unresolved, ask or recommend based on actual requirements; do not introduce another service by default. For unsupported tools, explain the adapter gap before proposing changes. Use `single` and `generic` unless the repository structure or requested profile calls for another layout. Do not invent an application stack or required workstreams.
2. **Confirm content language once.** Infer a likely language from the user's current messages and existing project documents; treat it as a suggestion, never consent. If the user has not already explicitly chosen, ask: “You are writing in <language>. Should task titles/descriptions/comments and Confluence documentation use <language>, English, or another language?” Accept any language. Bundle this with other necessary setup choices. Save only the confirmed choice using `python3 scripts/project.py language --set "<language>" --apply` after generation. A saved nonempty `content_language` is the confirmed project preference; reuse it on resume, even if a later chat uses another language. Ask again only to resolve a requested change or contradiction. Conversation replies follow the user; skill instructions, CLI messages, identifiers and technical paths stay English. Do not translate existing human-authored content without a request.
3. Preview the local result:

   ```sh
   python3 <skill>/scripts/framework.py init <directory> --name "Project name"      --provider <selected-provider> --tracker <selected-tracker> --profile generic
   ```

   Pass the selected provider/tracker explicitly; omitted CLI options have fixed defaults that do not establish user preference. Add `--adopt` for an existing project or `--kind workspace` for multiple repositories. Inspect conflicts and warnings. Use an adoption branch when Git already exists. Apply within the authorized scope with `--apply`; add `--git` only to initialize Git if needed. The generator makes no commits or remote resources. A preview is not an extra approval gate.
4. Complete `.project/config.json` with purpose, confirmed content language and real verification commands (argument arrays, no implicit shell). In a workspace register commands per repository. Review `.project/adoption.json` against actual files and checks before marking it reviewed; file inventory is not verification. Preserve project CI and integrate checks only after inspecting it.
5. Reuse the project's planning format. If OpenSpec is selected, install it using `python3 scripts/project.py openspec --apply`. It uses the included lockfile, OpenSpec 2.0.0 and both clients' core workflows, with Node >=22.12.0. Validate `python3 scripts/project.py spec list --json`. A plan does not require OpenSpec; do not install a second planning system solely because work spans several tasks.
6. For remote setup, read [references/integrations.md](references/integrations.md). Discover tools in the current client. For each resource establish existing, new or deferred, reusing explicit prior choices. Before creating anything resolve destination, name and visibility. Confluence is optional. Its human-authored hub has a separate generated **Project map** child. `project.py hub` produces an English draft and a manifest carrying the content language; translate only its prose to the confirmed language before publishing, keeping JSON keys, identifiers and URLs intact. If language is unconfirmed, collect the choice before creating or updating task/document content. Read access does not prove write permission; stale probes need refreshing after a wait.
7. Run `doctor`, session `preflight --live`, actual client read probes where required, and `verify`. Distinguish structural readiness, application verification, configured hooks and actual client activation. Report `not_configured`, `not_verified`, failed and pending outcomes explicitly.
8. For existing projects, offer content onboarding after local setup: [references/onboarding.md](references/onboarding.md). Propose the page tree, grounded drafts and outstanding work before creating remote pages or tickets. Prior permission for local adoption does not authorize publication.

## Delivery and maintenance

Report the actual version, local changes, commands/results, confirmed or pending language, and remaining client/service checks. Never turn a saved URL, manual attestation or passing structural check into a claim of verified service behavior.

An interrupted `init`/`update` must use `framework.py recover <directory>`, first preview then `--apply`; do not delete the recovery journal. Before updating, follow the language procedure in [references/procedure.md](references/procedure.md#language-during-updates): managed instructions remain English; project content retains its confirmed language. For daily work use generated `AGENTS.md` and `.project/WORKFLOW.md`, rather than loading this whole skill again.

External documentation and integration boundaries: [references/sources.md](references/sources.md).

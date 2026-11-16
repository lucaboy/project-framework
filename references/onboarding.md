# Content onboarding for an existing project

Use after conservative local setup when the user wants existing code, notes and unfinished work organized into useful documentation and tasks. This is a bounded onboarding step, not continuous automatic project documentation. It may be deferred without blocking coding.

## Gather evidence

Inspect user-designated notes, current repository documents, entry points, manifests, contracts and CI. Distinguish current code from notes, proposals and hypotheses. Inspect relevant unmerged branches, unpushed commits, worktrees, existing PRs/issues and known TODOs without pushing or closing anything. Use commit history and the stated context to assess age; file modification time is not reliable evidence of currency.

Record repository revisions and how another reader can retrieve each important source. Local paths alone do not make evidence recoverable from a clone. Keep an authorized, redacted summary or a durable source reference; explicitly identify unavailable raw evidence and unpushed work. Do not import private archives merely to make every link portable.

Do not copy secrets, personal contacts, contracts or financial details into drafts or public repositories. Reference their authorized source where needed. Technical identifiers are useful evidence; uncertainty about disclosure should be resolved before publication.

Read the confirmed `content_language`. If unset, suggest the user's language and ask once before drafting content for the tracker or Confluence. English skill instructions do not imply English publication.

## Propose a documentation tree

For broad project onboarding, propose area pages with component pages underneath as the default navigation structure. Reuse a suitable existing hierarchy or flatten a small project only with a concrete rationale recorded in the coverage table. A requested single-page correction does not require reorganizing the whole documentation tree. Use `.project/TEMPLATES.md` and explain each page's purpose and authoritative source. Technical truth stays versioned with code; a business/product page may be authoritative on Confluence. Avoid duplicating existing pages and avoid treating every directory as a component.

Before drafting, inventory the relevant areas and independently meaningful components. Maintain a reviewable coverage table with `Area/component | Reader question | Authoritative source | Target page | Status/evidence | Exclusion rationale`. Every in-scope component needs a page or an explicit, justified location in a shared page; missing knowledge is an open gap, not silently out of scope. Record proposed exclusions for review.

Obtain agreement on the tree and coverage before producing extensive drafts. For an already explicit page request, that request may supply the agreement. Confirm the space's diagram renderer before choosing publication format.

## Draft from actual files

Keep local drafts in ignored `.project/local/onboarding/` while awaiting publication. For durable technical sources, prepare the relevant versioned document/diagram in the appropriate repository; an ignored draft alone is not a cross-computer handoff.

Use the relevant area/component templates as drafting aids; omit topics that do not apply. Inspect implementation files, not just README summaries. Describe current behavior, integration points, release/check entry points and surprising constraints. Keep useful rationale; do not pad short components to meet a word target. Link known source paths and commits. Clearly distinguish code evidence, notes and open questions. Review material claims and source references against actual files; do not use a fixed number of spot checks as proof that the whole page is correct.

Check related repositories before declaring an integration or operational dependency unknown. Separate a configured job from proof that it runs in production, and a historical rollout sequence from a rule for future changes.

For diagrams, keep the editable source and text explanation. Confirm rendering support, or plan a rendered image fallback. Do not call a code block a visible diagram. Read `.project/TEMPLATES.md` for diagram rules and [integrations.md](integrations.md) for site-specific draw.io considerations.

## Completeness review

Use the quality gate in `.project/TEMPLATES.md` before describing onboarding as complete. Reconcile every coverage-table row with the actual page and its evidence. A page title, component inventory or source link alone does not explain behavior. Unresolved gaps must be reported as partial coverage, with the missing source or decision identified.

Reconcile the entry points too: README, document index, generated map and ticket links must describe the resulting project. Remove resolved questions and drafting placeholders; confirm that references to guides, components and created parent issues point to real destinations.

For an operational guide, follow its instructions from the stated prerequisites to the expected result where execution is permitted. For an explanation, check that an unfamiliar reader can identify responsibility, interactions and constraints without reconstructing the entire codebase. Request independent review when available; if it was not performed, say so. Word counts and page hierarchy do not prove technical accuracy or usability.

## Review and publish

Present concrete drafts, evidence gaps and destination pages for user review before creating or updating remote content. Remove temporary drafting markers from approved text while retaining unresolved uncertainties as explicit open questions. Do not infer publishing permission from the earlier local adoption request.

Publish approved ordinary pages in the agreed tree and language. Read back each created/updated page and inspect diagrams in the browser where possible. Register technical sources with `project.py doc`; mark `--published` only after the actual publication is observed. Register Confluence-only sources with `--page-url` and no source path; they remain `page_authoritative`, not remotely verified by Python. Refresh the generated map while preserving the human hub.

## Turn unfinished work into a backlog

Separate ready-to-act work from items requiring clarification. Check for existing equivalent issues and link evidence; old notes are not automatically approved tasks. Present proposed issues with scope and acceptance criteria for selection. Create approved epics first, then child issues using returned keys and supported parent relationships. Read back actual links. Replace drafting placeholders such as “epic to create” in owned generated content after the real keys exist.

Do not infer assignments, issue transitions, completion or permission to push old branches from a list of notes. Follow `.project/WORKFLOW.md` for claims and subsequent execution.

## Handoff

Report created/updated pages and issues, source locations, reviewed versus unverified claims, open questions, excluded sensitive/stale material, and any unpushed work. A connector write or a rendered page is not evidence that described software passes its checks.

# Working protocol

A **task** produces one verifiable outcome; an **initiative** coordinates several. Define scope and acceptance criteria. Separate concurrent task contexts. Scale planning to risk/dependencies, reuse project conventions and existing authorization; phases are not additional approval gates.

Use the confirmed `content_language` in `.project/config.json` for task/document prose. If empty, suggest the user's language, English or another choice; save explicit consent with `project.py language --set "<language>" --apply`. Reuse it on resume. Do not translate existing content automatically; instructions and identifiers stay English.

## 1. Request and ownership

1. Reuse the matching tracker issue. If disconnected, use `LOCAL-1`, `LOCAL-2`, etc. and hand off proposed remote text.
2. If missing, use `.project/TEMPLATES.md`. `automation.tracker` selects the project convention, within the user's authorized scope: `guided` creates one issue for the requested task; for an initiative, create the epic, propose a plan, then create task issues after plan approval. `automatic` also creates the task issues without waiting for plan approval. `manual` proposes issues for confirmation. Host/user restrictions and language confirmation still apply.
3. Keep one issue per result, usually per repository involved. Implementation checklists stay in the chosen plan (for example OpenSpec's `tasks.md`), not in a ticket for each coding step.
4. Read the current owner and status before claiming. Stop if another owner is active. Use conditional updates/version checks if the service provides them, then assign, transition and add the Started comment using supported calls. Read back ownership and status before editing code. These operations may be separate and are **not a distributed lock**. If agents share one account or race, record the agent/session and branch in the comment and coordinate a single claimant before proceeding. A local checkpoint cannot arbitrate remote ownership.

Write only within the configured tracker project/Confluence space. Deletion, permission changes, messages or writes elsewhere need explicit authorization. Preserve human-authored content; comment or propose corrections. Whole-body updates may lose rich content: use current tool schemas and fresh versions for authorized targeted edits.

## 2. Execution

- Use a task branch, such as `APP-123-password-reset`. Concurrent agents in one repository need separate worktrees; in a workspace: `git -C repos/NAME worktree add ../NAME-APP-123 -b APP-123-password-reset`.
- In a workspace use `git -C repos/NAME`. `project.py repos --update` explicitly fetches and fast-forwards clean default-branch checkouts; other branches and dirty trees remain in place.
- Run `python3 scripts/project.py verify`; in a workspace use `verify --repo NAME`, or `--repo NAME=PATH` for a worktree. Repeat after interruption or changes to sources/checks/environment. A commit with identical sources does not invalidate the proof.
- A repository without checks cannot deliver verified software. Establish a meaningful check first.
- Request independent review of the diff and acceptance criteria using `.project/REVIEW.md`.
- Shared checkpoints, document registry and plans belong in the workspace. Serialize edits to that shared checkout, or use separate workspace branches and integrate them before handoff; do not have parallel agents commit on a shared main branch. CLI locks cover one checkout only, not manual edits.

## 3. Initiatives

Resolve scope and dependencies, link a concise plan in the project's chosen format, and obtain any missing approval before implementation. Reuse prior approval; pause at agreed milestones. Version shared contracts first. OpenSpec is optional: use `openspec/` and archive workflows only when selected. Otherwise maintain and close the authoritative plan where it lives.

## 4. Documentation

Maintain relevant documents; templates do not require additional workstreams. Version contracts and diagrams with code. Register authoritative locations for other decisions. Confluence, when selected, projects merged technical sources or holds registered authoritative pages. Without it, maintain the chosen documentation and skip remote publication. Before publication, apply the documentation quality gate in `.project/TEMPLATES.md`.

1. Update the technical source in the task branch, covering current behavior as well as the change.
2. Register it once: `python3 scripts/project.py doc --id ID --type api --title "..." --source repos/backend/docs/openapi.yaml --apply`. Types: `api`, `flow`, `infrastructure`, `other`. For a Confluence-only source use `--page-url` without `--source`.
3. After merge, render and publish in the confirmed language using `.project/TEMPLATES.md`. Read back the result and inspect diagrams. Then attest publication: `python3 scripts/project.py doc --id ID --page-url URL --published --apply`. This attests a hash, not remote equality.

`project.py docs` lists source changes requiring publication. `page_authoritative` means only that a page URL is registered, not that its content or access was checked. Changing the source path or page URL clears previous publication evidence.

With `automation.documentation=guided`, update owned generated pages within scope and list proposed new pages for confirmation without stopping unrelated work; `automatic` also creates new pages, and `manual` proposes all remote edits. Regenerate the **Project map** child with `project.py hub` when repository/document links change. Translate draft prose to the confirmed language and preserve its JSON manifest. Never replace the human-authored hub.

## 5. Delivery

Software delivery follows the repository path below. Other deliverables record reviewed artifacts and evidence without a code merge.

1. Push the branch and open a PR when authorized by the task and host, unless the user excluded this. Include issue key, behavior, verification and review. Comment In review and save `--status review`. A person owns the merge unless explicitly delegated.
2. After the actual merge, update the clone, verify the merged checkout before a software `done` checkpoint, align documentation, comment Closed, and close the issue. Do not claim remote steps succeeded until their result is observed.

Comment at milestones; blockers state what is needed and from whom.

## 6. Checkpoints and handoff

Before cross-computer handoff, commit code first, refresh the checkpoint, then commit/push it. A null `git_head` cannot identify recoverable code.

```sh
python3 scripts/project.py checkpoint --task APP-123 --owner codex-session-1 \
  --summary "Password reset" --status in_progress \
  --completed "Defined API contract" --next "Implement and test single-use token" --apply
```

`docs/tasks/APP-123.json` holds current state within 200 words; Git holds history. In a workspace add `--repo NAME` or `--repo NAME=PATH` for each affected repository. Software `review`/`done` requires a current passing proof. Other domains need `--evidence`; the CLI checks presence, not truth. Coordinate an ownership change in the tracker before using `--transfer-from`.

To hand off, save and push code branches and the checkpoint branch, then reassign the issue. Recipients run `doctor`, retrieve `git_branch`/`git_head` from `revision`/`repository_revisions`, restore dependencies/access and verify that checkout. Starting from main alone does not resume unfinished work. Worktrees isolate files, not databases or ports; arrange those separately.

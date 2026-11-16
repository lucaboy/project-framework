# Multi-repository projects

A workspace is a small coordination repository; application repositories keep independent histories and pipelines.

| Location | Contents |
| --- | --- |
| Workspace (`--kind workspace`) | Workflow, repository registry/checks, language preference, shared plans (OpenSpec when selected), checkpoints and document index |
| `repos/<name>/` | Independent application clones, ignored by the workspace Git repository |
| Component (`--kind component`) | Short AGENTS instructions, CLAUDE import, template manifest and template license; no project helper scripts |
| Optional Confluence hub | Human context plus generated Project map child pointing to the workspace and component documents |

Start the agent at the workspace root for cross-repository work. When opened independently, a component cannot assume its parent workspace instructions are loaded, particularly in cloud sessions. Its short instructions and real verification entry point must be sufficient to operate safely.

## Setup

Existing clones/worktrees elsewhere stay in place. To continue their work, push and fetch the branch into `repos/`, or deliberately move the complete clone there. `repos --apply` leaves populated directories alone. Report unpushed commits rather than creating an unrelated fresh task checkout.

1. Follow SKILL.md with `--kind workspace`, usually `--profile generic`. Set purpose and confirmed content language. Top-level application `commands` are unused; checks belong to components.
2. For each component establish existing/new/deferred. For new repositories suggest `<slug>-<role>` and confirm the remote destination before creation. Register real verification entry points:

   ```sh
   python3 scripts/project.py repo --name backend --role "API and data" \
     --url https://github.com/ORG/REPOSITORY --commands '[["npm", "test"]]' --apply
   ```

   Prefer an existing script or Make target to copying pipeline internals. If checks do not exist, omit them and report the gap: `verify` lists it under `not_verified`.
3. `repos` shows status; `repos --apply` clones missing repositories using local Git credentials (`--ssh` selects SSH). `repos --update` explicitly fetches and fast-forwards clean default-branch clones; it does not switch task branches.
4. Add short instructions to each component on a task branch. When the tracker is unavailable, `chore/project-standard` can be a temporary setup branch; otherwise use the issue key:

   ```sh
   python3 <skill>/scripts/framework.py init repos/backend --name "Project name" \
     --kind component --workspace-url https://github.com/ORG/WORKSPACE --adopt
   ```

   Inspect the preview and add `--apply`; for an empty new repository omit `--adopt` and add `--git`. If the workspace URL is not known, add it later with `framework.py update repos/backend --workspace-url URL --apply`. Read adoption notes even though components have no separate adoption review file. Put the verification command and repository conventions in AGENTS.md outside the managed section; link pipeline details instead of copying them.
5. Complete relevant setup steps from SKILL.md. Preflight includes registered repositories. Propose the workspace snapshot and component PRs; inspect release triggers before merging instruction changes. Where needed, exclude AGENTS.md, CLAUDE.md and `.project/` from release archives while preserving required license notices for distributed template code. Link the workspace before the initial component PRs to avoid a second round. Regenerate the map when registry entries change. Offer content onboarding for existing projects.

## Checks and concurrent work

`verify` checks configured cloned repositories; `verify --repo backend` selects one. Use `--repo backend=PATH` for its worktree and the same selector in the checkpoint. Different repositories can be verified by concurrent processes; checks for the same registered repository are exclusive within the workspace checkout. Evidence is one record per repository and may be replaced by a later worktree check. Different workspace clones do not share locks or reports.

Workspace CI checks only the coordination structure, not private application repositories. Each component's pipeline must execute its real checks. An empty workspace check set is not application verification.

Before merging across repositories, identify shared deployment targets, databases, locks and operational jobs. Independent repository pipelines do not imply independent releases. Record the delivery order and, when the target permits only one operation, wait for each release to finish before triggering the next. If a retry still finds the target occupied, inspect the actual owner or hand off the blocker; do not remove locks or repeatedly rerun unchanged jobs. Record merge, validation and deployment outcomes separately.

Coordinate edits to the shared document registry/plans/checkpoints. Separate application worktrees do not isolate workspace metadata. Use one metadata writer or separate workspace branches integrated before handoff. The tracker owns task assignment; Git/checkpoint conflicts require normal resolution. Keep component contracts with their code and shared cross-repository decisions in the workspace or their single registered authoritative page.

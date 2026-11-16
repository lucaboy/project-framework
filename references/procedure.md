# Generation, adoption and updates

## Initial choices

Inspect existing tools and reuse user choices. The generator supports GitHub + GitHub Issues, GitHub + Jira and Bitbucket + Jira. Pass the selected provider and tracker explicitly: CLI defaults are not evidence of a project preference. Resolve missing choices from actual requirements. Confluence is optional. Do not migrate repositories or combine backlogs as a side effect; identify unsupported integrations instead of silently replacing them.

`single` is one repository; `workspace` and `component` support multiple repositories (see [workspace.md](workspace.md)). `generic` chooses no stack. `web` adds areas to map for frontend, backend and infrastructure, without imposing frameworks or code directories. Documentation stubs are not completed reviews.

Follow SKILL.md's language confirmation step. Store the chosen language only after explicit consent; existing projects with no `content_language` return a pending state. Do not infer a new preference from OS locale or a resumed chat.

## Create and adopt

`framework.py init` previews; `--apply` writes locally; `--git` initializes Git if absent, without a commit. A directory containing only `.git` is new. The generator warns about destinations inside another repository and does not create a nested repository there: CI/hooks normally need the repository root.

With `--adopt`, code, documents and pipelines are preserved. Managed sections are appended to README, AGENTS, an existing AGENTS.override, CLAUDE and ignore files. An existing CLAUDE import of AGENTS is not duplicated. JSON hooks are merged additively; existing TOML configuration is preserved. File permissions remain intact. Reserved-path collisions, malformed JSON and symbolic links stop planning before writes. This includes a CLAUDE symlink to AGENTS: propose replacing it with a regular `@AGENTS.md` import file rather than silently removing the link.

`.project/adoption.json` inventories manifests and pending review; it does not execute discovered scripts. A recognizable credential-free origin URL and detected default branch are retained. Inspect actual manifests, configure real checks, resolve conflicting instructions and integrate `doctor`/`verify` into existing CI without removing needed checks. Only then set `status` to `reviewed` with concrete check/results in `evidence`. A pipeline not yet run remotely must be identified as such. `application_commands_executed` remains empty because it describes the generator, not later agent work.

A dry run is a technical preview, not a mandatory approval request. Apply when local edits are authorized. `--apply` grants no external permission. Do not put tokens in command arguments: the verification report records them. Shell-dependent commands must name the shell explicitly and be reviewed as code.

## OpenSpec

Install only when OpenSpec is the selected planning workflow. Existing specifications or another agreed planning format can satisfy the method; a multi-task initiative alone does not require this dependency. `project.py openspec --apply` runs `npm ci` from the included lockfile with install scripts disabled, then OpenSpec **2.0.0**, profile `core`, tools `codex,claude`. It does not use `--force`; inspect existing OpenSpec layouts before migration.

Check all six core workflows for both clients (listed in `.project/dependencies.json`), including `.agents/skills/openspec-propose/SKILL.md` and `.claude/skills/openspec-propose/SKILL.md`. Version generated workflows in the project, not personal profiles, caches or credentials. Replace `openspec <arguments>` in workflows with `python3 scripts/project.py spec <arguments>`; check `spec list --json`. The CLI stays under ignored `.project/local/`, so restore it on a new computer when needed. English OpenSpec context points to the confirmed content language; adopted project-owned OpenSpec configuration needs manual reconciliation if it hardcodes a different language.

## Verification and checkpoints

Preflight reports are ignored, session-specific access evidence. Complete MCP probes in the client using `.project/INTEGRATIONS.md`. Hooks require actual client support and trust; distributing their files does not activate them. AGENTS.md supplies the manual path when hooks are unavailable.

`verify` runs configured commands without an implicit shell, recording commit, Git state and a source fingerprint. No checks returns exit 2; failed checks or checks that change sources fail. Fingerprints cover content, file type and executable bits for tracked/nonignored files, excluding checkpoints and known untracked local caches/output. Initialized submodules include checkout contents and revisions recursively. An uninitialized submodule blocks verification but permits an in-progress checkpoint. Without Git the script cannot apply `.gitignore`.

Evidence is current only while sources, commands, timeout, repository target and verifier code match. Identical-source commits and checkpoints do not require another run. Workspace checks are per repository; explicit worktree paths must share the registered Git repository. Before running commands the script saves `incomplete`, so interruption cannot revive an old pass. OS locks serialize checks of one registered repository within the same workspace checkout; different repositories can run concurrently and merge their reports. One proof is retained per repository: checking another worktree replaces it. Locks and reports do not coordinate different workspace clones/computers.

Timeouts and catchable interruptions attempt to terminate the check's process tree before releasing its lock. Forced process termination, detached descendants and platform-specific process behavior require separate care; do not claim this is a sandbox. Proofs do not certify ignored dependencies, environment variables or external services. Rerun when those change.

Software `review`/`done` checkpoints require a current passing proof; other domains require a manual evidence reference, whose truth is not checked. Metadata CLI writes are serialized within one checkout. Tracker claims, manual file edits and cross-computer merges still require coordination.

## Update

Run `framework.py update <directory>` on a branch based on a saved Git state, and repeat for each component repository. If there is no commit, the plan warns that rollback/review lacks a baseline; arrange an initial snapshot before applying an update.

The manifest stores version, options and distributed hashes. Updates change untouched managed files or delimited sections. Project-owned configuration, documents, hooks, CI, OpenSpec and checkpoints are preserved; removed templates are not deleted. Inspect the language impact below before applying.

A conflict needs three distinct versions: recorded template base, project content and new template. If upstream did not change a locally edited file, no conflict is raised. On conflict, exit 2 and zero writes; `diffs` shows project (`-`) versus skill (`+`). Integrate the needed changes manually, then preview again with `--keep <path>` for each conflict. With `--apply`, this retains the project file and records the new upstream base. It does not verify your manual integration; omitted upstream changes are not proposed again until a later upstream change. Restore missing managed-section markers before retrying.

Downgrades are refused. Increment VERSION for template changes. For a component, `update --workspace-url URL` adds the known workspace URL.

## Language during updates

`content_language` controls authored task/document prose; it does not localize distributed instructions or the CLI. `framework.py update` warns that managed text is supplied in English. It does not detect the previous language or translate project-owned files.

| Material | Update behavior | Authoring rule |
| --- | --- | --- |
| Managed instruction sections, `.project/` rules and `docs/GUIDE.md` | Unmodified managed material can be replaced by English templates; local changes can conflict | Keep execution rules and template prompts in English |
| Project-owned documents, README prose outside managed sections, config and existing OpenSpec context | Preserved | Use the confirmed content language for authored prose |
| Hub output and issue/page template examples | English source/draft, not a finished localized publication | Write or translate the resulting content in the confirmed language before publishing |

1. Save the current project state in Git. Inspect `.project/template-state.json`, `git diff` and the saved `content_language`. If the preference is unset, confirm it before drafting task/document content.
2. Run `python3 <skill>/scripts/framework.py update <directory>` without `--apply`. Review listed files, warnings and any conflict diffs. For an ordinary replacement, compare the current managed file/section with its corresponding asset in the skill; the plan lists replacements but does not print every non-conflicting diff.
3. Separate changes to execution rules from changes to project prose. If a managed file was locally translated or customized, integrate the new behavior manually and follow the conflict/`--keep` procedure above. `--keep` works only for actual conflicts; do not edit recorded hashes or versions to bypass review.
4. Apply the reviewed update. Verify that `content_language` and project-owned documents were preserved. In project-owned OpenSpec context, reconcile any explicit language rule with the confirmed preference; edit only that rule and retain project-specific requirements.
5. Generate drafts, fill template fields and translate their prose to the confirmed language. Preserve commands, paths, links, JSON keys, identifiers and source/evidence distinctions. Review clarity in that language; a literal translation is not a substitute for complete content.
6. Run `doctor` and the relevant checks, then review the Git diff. Remote content is updated only within authorization and checked by read-back. Report language changes separately from framework updates; do not report existing pages translated unless they actually were.

This procedure separates managed instructions from project-owned prose; it does not automatically translate existing project content.

## Recover an interruption

`init --apply` and `update --apply` first save `.project/local/framework-pending.json`. Run only one framework operation per destination at a time. After interruption use:

```sh
python3 <skill>/scripts/framework.py recover <directory>
python3 <skill>/scripts/framework.py recover <directory> --apply
```

Recovery completes the saved plan even if the skill has changed: already-applied files remain intact, original-state files receive planned contents, and pending Git initialization is completed. The manifest is written last. This is forward recovery, not rollback.

Any file that matches neither original nor planned content blocks all writes. Preserve subsequent edits separately, compare against Git and the journal, restore a recognized state, recover, then reintegrate edits. Do not forge journal hashes or delete the journal to force adoption. It may contain existing configuration text: keep it local and never commit an incomplete setup, especially a component without a local ignore rule.

## Report

State actual path/version/profile/provider/tracker, confirmed language, commands/results and remaining steps. Distinguish structure, OpenSpec setup, application checks and remote access; local configuration is not a published service.

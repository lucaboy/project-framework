# Project Framework

**Version 1.0.0 · First public release · MIT · Python >=3.10**

A methodological framework for agent-assisted project work. It defines how to establish intent, scope a task, plan changes, execute them, verify outcomes and preserve the decisions needed to continue.

The method is expressed as project instructions, reusable templates and executable checks. It can be introduced into an existing project or used from the start. The skill configures the workflow; generated project instructions guide its day-to-day application.

## How it works

1. **Understand the work.** Read the relevant sources, identify the requested outcome and define observable acceptance criteria.
2. **Plan at the right scale.** Use a bounded task for a small change; record a plan and dependencies when the work spans multiple outcomes. Reuse the project's planning conventions.
3. **Establish responsibility.** Identify the authoritative task record, active owner and affected repositories. Coordinate dependencies before parallel execution.
4. **Execute and verify.** Isolate changes, run the relevant checks and review the result against its acceptance criteria. Missing or stale evidence remains explicit.
5. **Integrate and preserve context.** Complete authorized delivery steps, update authoritative documents and record the state needed to resume.

These phases define the information and evidence each step needs. They do not require a new meeting, document or approval for every change; reuse decisions and authorization already supplied.

## Principles

| Principle | Practical consequence |
| --- | --- |
| Explicit authority | Each task, decision and document has an identified source of truth; projections link back to it |
| Proportionate process | Task size, risk and dependencies determine planning and review effort |
| Evidence before completion | A passing structural check, saved URL or intended action is not proof of the outcome |
| Durable context | Scope, decisions, verification and unfinished work remain recoverable outside a chat |
| Conservative adoption | Existing code, documentation, automation and project conventions are inspected and preserved |
| Coordinated concurrency | Parallel work has distinct scopes, ownership and isolated changes; local locks are not distributed coordination |

## Implementation and supported tools

The method does not prescribe a team size, application architecture or deployment model. This package provides a concrete implementation for Git-based projects and Codex/Claude Code; support for additional clients or platforms requires an adapter and validation.

| Capability | Included implementation |
| --- | --- |
| Project instructions | Codex `AGENTS.md`, Claude Code import, shared workflow and optional client hooks |
| Repository setup | GitHub or Bitbucket; single repository, workspace and component layouts |
| Task tracking | GitHub Issues or Jira; one configured authoritative tracker, with local IDs when disconnected |
| Planning | Existing project conventions; optional pinned OpenSpec integration |
| Verification | Configured commands, checkout-bound evidence and provider-specific CI templates |
| Documentation | Versioned sources and an optional Confluence projection with registered authoritative pages |
| Continuity | Task checkpoints, repository revisions and access/dependency checks on resume |

Currently supported provider/tracker combinations are GitHub + GitHub Issues, GitHub + Jira and Bitbucket + Jira. Choose from the project's existing tools and requirements; no combination is a methodological requirement. Confluence and OpenSpec are optional. Using a different service does not imply that the bundled scripts support it.

The package also provides dry-run adoption, conservative template updates and interruption recovery. English instructions and CLI messages are separate from the user-confirmed language of task/document content. Example documentation topics are starting points, not required project workstreams.

Python >=3.10 and Git support the local workflow; the helpers use the Python standard library. OpenSpec 2.0.0 requires Node >=22.12.0 and npm only when selected. Remote authentication, permissions, execution and account limits belong to the actual service/client.

## Install the complete skill

Clone the release repository, then preview an installation:

```sh
git clone https://github.com/lucaboy/project-framework.git
cd project-framework
```

Add `--apply` to one installation command when intended:

```sh
python3 scripts/install_skill.py --client both
python3 scripts/install_skill.py --client both --project /path/to/project
```

Choose personal or project installation, not both. Codex uses `.agents/skills/project-framework`; Claude Code uses `.claude/skills/project-framework` (or its configured personal directory). `--base /temporary/directory` supports an isolated test. Existing installations are never overwritten. Open a new client session and verify discovery. Copy the **whole package**, not SKILL.md alone.

Invoke `$project-framework` in Codex or the corresponding discovered skill in Claude Code. For example: “Apply the project methodology to this repository: establish authoritative sources, task and planning conventions, verification criteria and delivery checkpoints. Reuse the existing tools and preserve project-owned content.”

The agent suggests a content language from your messages and asks for confirmation unless you already chose it explicitly. A saved choice is not silently changed by a later conversation language. Existing human content is preserved.

## Local CLI

```sh
python3 scripts/framework.py init /path/to/new-project --name "Example" --git
python3 scripts/framework.py init /path/to/existing-project --name "Example" --adopt
python3 scripts/framework.py update /path/to/project
python3 scripts/framework.py recover /path/to/interrupted-project
```

These are previews; add `--apply` to write. Supply `--provider` and `--tracker` for the selected supported tools. The CLI defaults to `github`/`jira` when omitted; these are implementation defaults, not a recommendation to introduce Jira. Read warnings and diffs. The generator does not run application commands, commit code or create remote resources. In a generated project, configure real checks and run:

```sh
python3 scripts/project.py language --set "English" --apply
python3 scripts/project.py doctor
python3 scripts/project.py verify
python3 scripts/project.py status --text
```

Use the user's confirmed language in the first command. `doctor` checks structure and warns about remaining setup. `verify` checks only configured commands; it is not a general certification of correctness or security. `preflight --live` performs configured read-only probes; writes to remote services remain agent/client actions within user authorization.

Most configuration commands preview unless `--apply` is supplied. Explicit execution commands (`verify`, `preflight`, `spec`) and `repos --update` are not dry runs. `repos --apply` clones missing repositories; `openspec --apply` downloads pinned dependencies locally. No helper pushes, creates PRs, publishes pages or sends messages.

## Repository structure and resuming work

Use `--kind workspace` for the coordination repository, register components with `project.py repo`, and clone them under ignored `repos/`. `--kind component` adds short standalone instructions and template provenance without duplicating the workflow runtime. Application repositories keep their own pipelines. Use separate task branches/worktrees; coordinate shared workspace edits and tracker claims.

On another computer, clone the workspace/project, retrieve the checkpoint's code branches/commits, restore dependencies and client access, and verify that checkout. Do not initialize again. Unpushed work, credentials and ignored local evidence do not travel with Git. Remote execution requires a supported client/provider environment; GitHub and Bitbucket integrations are not assumed equivalent.

## Boundaries

Local scripts enforce the file and evidence checks covered in [VALIDATION.md](VALIDATION.md). Language confirmation, tracker ownership, evidence attestation and publication discipline rely on agents following instructions and host permissions. Local locks do not arbitrate multiple computers or manual edits. Confluence-only page registration is not verification of that page. Hooks require client support and trust; a config file is not proof of activation.

The full suite passed on macOS and Linux, including the declared Python 3.10 minimum. Native Windows CI passed 28 core checks, with two POSIX-specific cases skipped; it does not run the full Unix suite. On Windows use `python` or `py -3`; bundled shell hooks need a compatible shell and supported client (for example Git Bash), otherwise use the manual preflight path. Container and mocked/path-level tests do not certify every host or client environment. See [VALIDATION.md](VALIDATION.md) for the exact client and service checks.

Updates preserve project-owned content; managed instruction/template text is supplied in English. Follow the [language update procedure](references/procedure.md#language-during-updates) to inspect replacements, resolve local edits and author task/document prose in the confirmed language. Removed files are not deleted automatically.

## Maintenance

Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`. Tests generate disposable projects and local Git fixtures; no service credentials or remote writes are needed. See [VALIDATION.md](VALIDATION.md) for results and limits, [SKILL.md](SKILL.md) for agent instructions, and [references/sources.md](references/sources.md) for the external documentation used by the integrations.

The framework establishes the project-level workflow. Specialized implementation practices can supply design, debugging, testing or review techniques within it. Reuse an existing practice when it meets the task's needs; resolve conflicting instructions explicitly rather than combining two mandatory workflows. Load supporting references only when relevant.

## License

[MIT](LICENSE). Generated projects include the template license notice in `.project/LICENSE`; retain it when redistributing substantial portions of the supplied material. Adopting this framework does not change the license of your existing code or documents. Downloaded dependencies retain their own licenses.

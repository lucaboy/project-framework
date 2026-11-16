# Release validation

**Project Framework 1.0.0 — first public release**
Review date: **2026-11-16**.

This report distinguishes automated checks, instruction-driven behavior and real-client/service limits. Private project names, identifiers and content are excluded.

## Automated checks

| Environment | Result | Scope |
| --- | --- | --- |
| macOS arm64 / Python 3.14 | 121 passed | Full local suite on a disposable package copy |
| macOS 15 Intel / Python 3.14 | 121 passed | Full hosted CI suite |
| Linux / Python 3.10 | 121 passed | Full hosted CI suite; declared minimum Python version |
| Linux / Python 3.14 | 121 passed | Full hosted CI suite |
| Native Windows / Python 3.14 | 28 passed, 2 skipped | 30 selected core cases; the skipped cases simulate POSIX locking |

[GitHub Actions](https://github.com/lucaboy/project-framework/actions) provides the actual per-commit results. The workflow declaration alone is not evidence of success. Linux arm64 container runs also passed. Native Windows coverage is a core subset, not the entire Unix suite.

The suite exercises:

- New projects, conservative adoption, provider/tracker combinations and repeated initialization.
- Preservation of code, documentation, CI, imports, hooks, overrides, permissions and project-owned edits.
- Workspace coordination with two repositories, separate proof records, worktrees and clone/resume.
- Interrupted initialization/update recovery, conflicts, malformed data, symlinks, reserved collisions and downgrade refusal.
- Empty, failed, timed-out and interrupted checks; changed commands, source files, verifier code, executable bits and submodules invalidating proof.
- Concurrent verification and metadata writes; one local checkpoint owner and preservation of simultaneous repository registrations.
- Confirmed content-language persistence through update/clone, explicit English-template update warnings, and preservation of project-owned human content.
- Publication-evidence invalidation when a source path or target page changes; exact preservation of mixed line endings outside managed sections.
- Bounded locking, explicit I/O errors, first-commit checkpoint warnings and session-bound access evidence.
- Windows Git path normalization, complete skill installation and template license notices.

All generated projects, installations, local remotes/clones/worktrees and dependency caches used temporary directories. No personal skill profile or customer project was modified by these tests.

Additional validation passed: the official skill validator, Python 3.10 grammar parsing, JSON/YAML parsing, local reference checks, package extraction and isolated installation for both clients. The entry instructions, generated workflow and supporting references were reviewed for consistent optional planning/documentation tools and project-specific choices. A disposable adoption preserved an existing plan and GitHub Issues configuration without installing OpenSpec. These checks validate packaging, generated instructions and script behavior, not model judgment.

The package consistently uses Project Framework identifiers: `scripts/framework.py`, `project-framework` section markers, the `project_framework` map key and the current session banner/recovery path. Recovery, managed-section updates, hook output and hub schema are exercised by tests.

Documentation coverage and usability are review obligations, not script-certified properties. Broad onboarding proposes an area/component tree with justified exceptions, maps each in-scope component to evidence and a document, and applies the template quality gate. Word counts alone do not establish completeness.

## Client and integration checks

| Check | Observed result | Limit |
| --- | --- | --- |
| Codex app-server 0.169.0-alpha.11.1 | Discovered `project-framework` with repository scope, enabled state, expected UI metadata and no load errors | Does not establish adherence by every model/client version |
| Fresh untrusted Codex project | Project hooks were not loaded; the client reported trust-dependent configuration disabled | Trusted interactive hook execution remains unverified |
| OpenSpec 2.0.0 | Temporary pinned installation initialized both clients, exposed six core workflows and passed `spec list --json` | OpenSpec remains optional; existing documents are not translated automatically |
| Independent forward scenarios | Conservative adoption preserved code/docs/CI, executed a real configured check and resumed from a clone; another scenario persisted a non-English language choice | Simulations do not guarantee every future agent follows the protocol |
| GitHub CLI and connector | Authenticated private repository reads succeeded; authorized branch pushes and PR creation were read back, with passing validation jobs | Branch policy and deploy consequences remain repository-specific |
| Atlassian connector | Project, board, issue and space reads succeeded; issue creation, assignment, transition and targeted description edits were read back | Sequential operations do not establish atomic claims across agents |
| Confluence | Eight pages and an owned generated map were published and read back; edited text, map JSON and ten existing diagram references were checked. A browser check confirmed revised text and one rendered diagram | This does not validate every page layout or changed diagram attachments |
| Release packaging | Archive extraction and isolated skill installation passed | Release assets must be compared with the published Git revision |

Service checks used explicitly authorized destinations. They do not establish general write permission or certify the applications described by the documentation. The command-level verification checks were also exercised on a private workspace with seven components, without running production deployment steps.

Confluence connector HTML and storage XML are distinct representations. Edits require the snapshot expected by the current connector schema and read-back verification. Existing diagram rendering does not prove attachment creation, replacement or synchronization. See [integration guidance](references/integrations.md) and [official sources](references/sources.md).

## Guarantees and limitations

| Level | What is established |
| --- | --- |
| Scripts | Planned conservative writes, recovery checks, checkout/check-bound verification, explicit pending/failed outcomes and local metadata serialization covered by tests |
| Agent instructions | Language confirmation, authoritative sources, task claims, honest attestations, review and handoffs; these depend on agents respecting the protocol |
| Actual services/clients | OAuth, account permissions, quotas, page rendering, trusted hooks, cloud execution and remote mutations require destination-specific checks |

Claude Code CLI was unavailable. Hook commands passed local subprocess tests, but trusted interactive hook execution in both clients remains unverified. Real-account Bitbucket access, distributed tracker claims and publication of changed diagram attachments remain untested. No cloud-agent implementation run was performed.

Local proofs do not attest ignored dependencies, environment variables or external services. Local locks coordinate cooperating commands in one checkout, not separate computers or manual editors. Forced termination and detached child processes are not a process sandbox. Updates do not automatically translate human content or delete obsolete files. A checkpoint cannot recover unpushed code, and a publication attestation is not an independent remote consistency check.

## Remaining validation gaps

- Trusted interactive hook execution in both clients and broader native Windows coverage.
- Real-account Bitbucket operations and cloud-agent execution.
- Concurrent task claims across independent clients, including shared-account races.
- Publication of changed diagram attachments and browser checks across all affected pages.

Passing local or hosted checks does not remove these limitations. Repeat destination-specific checks when clients, permissions, commands or project state change.

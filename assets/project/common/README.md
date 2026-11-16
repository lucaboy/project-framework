# @@NAME@@

Project methodology configured with `project-framework` @@VERSION@@: establish intent and scope, plan changes, coordinate execution, verify outcomes and preserve decisions. Adapt the workflow to the project's existing tools, conventions and acceptance criteria. No application stack was generated.

## First use

1. Define the purpose and relevant documents starting at `docs/INDEX.md`.
2. Confirm the language of tasks and Confluence content, then save it: `python3 scripts/project.py language --set "English" --apply` (replace English with the user's actual choice). Any language is accepted. Instructions and CLI messages stay English.
3. Configure actual checks in `.project/config.json` as argument arrays. Example shape only: `[["npm", "test"], ["npm", "run", "build"]]`; do not copy commands that do not apply. Workspaces register checks per repository.
4. Reuse the agreed planning format. If selecting OpenSpec, preview `python3 scripts/project.py openspec`, then add `--apply`. Plans can use other formats without installing it.
5. Run `python3 scripts/project.py doctor` and `python3 scripts/project.py verify`. Set integration links using `.project/INTEGRATIONS.md`.

At chat startup run `project.py preflight --live`. SessionStart hooks do this where supported and trusted; AGENTS.md requires the agent fallback. Complete MCP/plugin probes in the client with the current session ID.

Python >=3.10 is required; on Windows use `python` or `py -3` if `python3` is absent. Bundled shell hooks require a compatible shell (such as Git Bash on Windows) and actual client support; otherwise run preflight manually. OpenSpec @@OPENSPEC@@ needs Node >=22.12.0 and npm and installs only under ignored project-local paths. Run its workflows via `python3 scripts/project.py spec <arguments>`; restore the CLI with `openspec --apply` on a new computer when needed.

The starter CI checks PRs and the default branch. A single-repository project's empty command list fails application verification explicitly; workspace CI checks structure only. Configure application dependencies/checks in their real CI/cloud environments.

## Daily work

Outcome and scope → task and proportionate plan → execution → verification and review → authorized delivery → recorded state.

For people, see `docs/GUIDE.md`; for agents, `.project/WORKFLOW.md`. `project.py --help` lists commands; `status --text` shows local state. Push code branches and checkpoints before handing off to another computer.

Configuration is `.project/config.json`; template provenance is `.project/template-state.json`. The originating skill can update managed files with `framework.py update`. It does not hold this project's memory. Updates preserve project-owned configuration and documents.

Verification evidence applies to current sources/check definitions. After `incomplete`, wait for the active run or rerun after interruption. Recover an interrupted setup through the skill's `framework.py recover PATH`, first preview then `--apply`; do not delete its local journal to force adoption. Template license: `.project/LICENSE`; this does not change the application's license.

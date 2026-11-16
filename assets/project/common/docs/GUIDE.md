# Working with agents

A compact guide for project contributors. Detailed execution rules live in `.project/WORKFLOW.md`.

| Level | Content | Location |
| --- | --- | --- |
| Project | Users, goals, product and architecture | Hub, PRODUCT/ARCHITECTURE documents or their authoritative links |
| Area | Domain conventions and knowledge | Repository/directory instructions and area documents |
| Initiative | A broad outcome spanning tasks | Initiative record and agreed plan; OpenSpec when selected |
| Task | One verifiable result with an active owner | Issue, branch and checkpoint |
| Chat | Execution or independent review of a task | Codex or Claude Code |

Keep each active task's context bounded. Use separate chats for concurrent tasks or independent review, and start a fresh context when unrelated history obscures the work. Keep the same chat for corrections/questions about the current task. Concurrent chats need distinct tasks and branches/worktrees; keep their number within the team's review capacity.

Durable context must be saved and pushed before changing computers. Unwritten chat knowledge and unpushed code do not travel automatically. Resume from the issue, checkpoint and documents.

A useful request states outcome, scope and observable acceptance criteria. For a broader initiative, approve the plan before implementation. The user also decides new remote destinations, permissions, merges unless explicitly delegated, automation modes and the language of task/Confluence content. The agent suggests a language and records the confirmed choice; instructions remain English.

Use the tracker for ownership/status, the hub for context/document links and PRs for changes/evidence. `python3 scripts/project.py status --text` shows the local view; it does not replace the remote tracker. Ask for actual commands/results, correct misunderstandings early, save durable decisions, and keep secrets out of chats/repositories.

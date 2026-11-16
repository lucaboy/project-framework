# Project map

The topics below are optional starting points, not a required project taxonomy. Keep relevant topics, add the project's actual domains and remove unused stubs/links. Stubs explicitly identify missing context. Use the confirmed project language when authoring project content; these initial instructions are English.

| Area | Initial source | Purpose |
| --- | --- | --- |
| Product | [PRODUCT.md](PRODUCT.md) | Users, goals, scope and outcomes |
| Architecture | [ARCHITECTURE.md](ARCHITECTURE.md) | Components, data and contracts |
| UI | [UI.md](UI.md) | Flows, components and visual references |
| Infrastructure | [INFRASTRUCTURE.md](INFRASTRUCTURE.md) | Setup, environments and release |
| Security | [SECURITY.md](SECURITY.md) | Protected assets and relevant checks |
| Marketing | [MARKETING.md](MARKETING.md) | Audience, offer and approved messages |
| Clients | [CLIENTS.md](CLIENTS.md) | CRM link and delivery rules |
| Working together | [GUIDE.md](GUIDE.md) | Tasks, chats, handoffs and human decisions |
| Tasks | Tracker in `.project/config.json` | Authoritative priorities, ownership and status |
| Local status | `python3 scripts/project.py status --text` | Repository checks and open checkpoints |
| Published documents | `python3 scripts/project.py docs` | Registered sources, pages and publication needs |
| Plans and specifications | Project-selected location; `openspec/` when selected | Versioned scope, decisions and initiative plans |
| Checkpoints | `docs/tasks/` | Current resumable state |
| Workflow/access | `.project/WORKFLOW.md`, `.project/INTEGRATIONS.md` | Execution and access evidence |

When a product document is authoritative in Confluence, replace the local stub with its link. Record the decision identifier/version used by a software plan. Avoid two editable copies of one source.

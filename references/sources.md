# External references

These references document the clients and services used by the package. They do not establish access to a particular account or prove that an integration has been tested. Use the schemas and permissions exposed by the current client; see [VALIDATION.md](../VALIDATION.md) for observed results and remaining gaps.

## Agent clients

| Documentation | Used for |
| --- | --- |
| [OpenAI: AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md) | Repository instructions and override precedence |
| [OpenAI: skills](https://learn.chatgpt.com/docs/build-skills) | Skill discovery, supporting resources and UI metadata |
| [OpenAI: hooks](https://learn.chatgpt.com/docs/hooks) | Session hooks and execution support |
| [Claude Code: memory](https://code.claude.com/docs/en/memory) | Importing shared instructions through CLAUDE.md |
| [Claude Code: skills](https://code.claude.com/docs/en/skills) | Skill discovery and resources |
| [Claude Code: hooks](https://code.claude.com/docs/en/hooks) | Hook configuration and execution |
| [Claude Code: MCP](https://code.claude.com/docs/en/mcp) | Client connections and authentication |

Hook configuration is not proof of activation. Check support and trust in the actual environment; the bundled shell commands require a compatible shell.

## Repository and documentation services

| Documentation | Used for |
| --- | --- |
| [GitHub repository API](https://docs.github.com/en/rest/repos/repos#get-a-repository) | Reading the exact repository and reported permissions |
| [GitHub CLI authentication](https://cli.github.com/manual/gh_auth_status) | Checking CLI authentication |
| [Bitbucket Pipelines](https://support.atlassian.com/bitbucket-cloud/docs/configure-bitbucket-pipelinesyml/) | Provider-specific CI configuration |
| [Atlassian MCP tools](https://developer.atlassian.com/cloud/rovo-mcp/guides/supported-tools/) | Runtime tool discovery and operation capabilities |
| [Atlassian MCP setup](https://developer.atlassian.com/cloud/rovo-mcp/guides/getting-started/) | Connection and authorization |
| [draw.io for Confluence](https://www.drawio.com/docs/tutorials/install-insert-diagram-confluence-cloud/) | The destination's diagram app and rendering |

Remote publication is an agent/client operation, not a Python helper capability. A successful read does not prove write permission. Confluence formats, app extensions and attachment behavior must be checked at the destination; no bidirectional document or diagram synchronization is provided.

## Optional planning integration

[OpenSpec](https://github.com/Fission-AI/OpenSpec) is an optional local dependency, pinned to [2.0.0](https://www.npmjs.com/package/@fission-ai/openspec/v/2.0.0). Its package and transitive dependencies are recorded in `assets/project/common/.project/tooling/package-lock.json`. Setup uses [npm ci](https://docs.npmjs.com/cli/v11/commands/npm-ci) with lifecycle scripts disabled. No installed OpenSpec implementation is included in the release archive.

Reuse the project's existing planning format when it already meets the task's needs. Selecting this framework does not require another specification tool or a change to the authoritative tracker.

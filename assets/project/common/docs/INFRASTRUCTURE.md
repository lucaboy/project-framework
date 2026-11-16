# Infrastructure and environments

Status: complete for the actual stack.

Describe setup, services, dependencies, development data and release procedure. Document variable names in `.env.example`; keep values in the environment's secret manager.

For concurrent work, allocate separate ports/databases where needed: a worktree isolates files, not services. Reuse local checks in CI/cloud; identify checks that require macOS or Xcode.

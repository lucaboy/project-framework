# Review criteria

The reviewer did not write the change and does not need the original chat. Supply the actual diff (including uncommitted changes when present), its base commit, and acceptance criteria from the issue or plan. The reviewer may read files but must not modify them.

Check, in order:

1. Acceptance criteria are implemented and have meaningful verification.
2. Existing behavior remains intact: callers, API contracts, migrations and configuration.
3. New failure and edge cases: missing input, permissions and concurrency.
4. Secrets or personal data accidentally included in code or logs.
5. Required API, flow or infrastructure documentation changes.

Report concrete correctness risks with file, line and practical consequence. Do not invent a target number of findings or request unrelated style changes. If none are found, say so. Summarize the result in the PR, including any limits of the review.

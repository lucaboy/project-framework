# Content templates

Use the confirmed project content language for filled-in prose. These English templates define structure, not the publication language. Prefer links over repeated issue/plan/code content. Lengths below are editorial targets. Explain material deviations in the coverage review; do not omit required explanations to meet a ceiling or pad prose to reach a minimum. The quality gate below is required regardless of length.

## Task issue (target: up to 120 words)

```text
Title: action + result, preferably under 70 characters
Outcome: what must be true at completion, in one sentence.
Scope: repository or area; relevant exclusions.
Done when: observable acceptance criteria.
Where to look: known files or paths; omit if unknown.
References: actual initiative, plan, page or contract; omit if absent.
```

## Initiative epic (target: up to 80 words)

```text
Title: user or business outcome
Expected result: one sentence.
Success measure: how success is observed.
Plan: link to the agreed plan or specification.
```

## Milestone comments (one concise comment per milestone)

```text
Started: branch <name>; agent/session <id>; plan <link if any>.
In review: PR <link>, or branch <name> awaiting authorized push; verification passed on <revision>.
Blocked: need <what> from <whom>.
Closed: <what changed>; updated documents: <list or none>.
```

## Human hub context (target: up to 150 words)

```text
Product: what it is, in two sentences.
Audience: users and primary need.
Status: current phase and next milestone.
Key decisions: concise linked decisions.
```

A person writes or confirms the context; an agent can propose an initial draft but does not overwrite it during routine updates. Repository, tracker and document links belong in the generated **Project map** child from `python3 scripts/project.py hub`. Translate that draft's prose to the confirmed language and preserve its machine-readable JSON.

## Area page (target: up to 400 words, plus diagrams/tables)

```text
Title: area name
Purpose: one or two sentences.
Current state: observed components in a list/table; diagram if the flow needs it.
Planned work: agreed but incomplete work, with actual issue links where available.
Open questions: what needs confirmation.
Sources: repository paths, or “this page” if authoritative; updated <date>.
```

For independently meaningful components, use `Component | Purpose | Page` and link a child page per component. Do not create a page solely to fill a template.

## Component page (target: 400–900 words, plus diagrams/tables)

For an independently meaningful component, such as a library, service, application or deployment unit. Use a stable, unique title. Sections should make sense when reached directly through search.

```text
Summary: purpose, users and current status, in at most three sentences.
Facts: type, repository, entry point, dependencies, verification entry point; provenance if derived from another component.
Behavior and boundaries: responsibilities and boundaries with other components.
How it works: the flow that requires reading several files, in numbered steps and a diagram when useful.
Integration points: Type | Name | Location (hooks, endpoints, jobs, tables, external services).
Configuration: option/secret names and storage locations; never secret values.
Release and verification: how to test and release, with a pipeline link.
Decisions and pitfalls: rationale, surprising behavior and known debt.
Sources: key paths; <repository> @ <short commit>; checked <date>.
```

Explain behavior and rationale that would otherwise take several code reads. Avoid inventories of classes/functions, copied signatures or dependency-version lists; link the source and explain why it matters. Ground claims in inspected files. Mark inference and unanswered questions explicitly; do not invent the historical rationale. Omit empty sections. A very small component may be better represented by a row in the area table. Length targets must not force filler.

## Documentation quality gate

For each in-scope area/component, verify these points against inspected sources. Record an explicit reason for a genuinely inapplicable item; unknown is not inapplicable.

- **Purpose and boundary:** explain the responsibility, intended reader and relationship to surrounding components.
- **Behavior:** describe the meaningful flow from entry point through processing/state to output, including relevant failure paths. An inventory of names is insufficient.
- **Interfaces and dependencies:** explain exchanged data, callers, external services and contracts, with source links.
- **Operation:** identify configuration locations, prerequisites, actual verification/release entry points and expected outcomes, or state what could not be tested. Never expose secret values.
- **Decisions and uncertainty:** distinguish observed behavior, requirements, rationale supported by evidence and unresolved questions.
- **Traceability and usability:** reference inspected paths/revisions; check links, rendered diagrams and that the reader can perform or understand the stated task without missing steps.

An area overview links to component detail instead of repeating it. A small component may share a page only if the required explanation is still present and the coverage table records where. A long page without these answers fails review; a shorter page can pass with complete relevant answers and a documented reason for the shorter form.

Use document purpose to choose the structure: procedures need prerequisites/steps/results, references need accurate contracts/options, and explanations need behavior and rationale. Separate these when mixing them obscures the reader's task. Do not add four empty document categories merely to follow a documentation model.

## Diagrams

Each diagram answers one question, such as request flow or release path. Keep labels consistent with prose and use a compact layout (roughly ten nodes is a useful starting point, not a hard limit). Include a nearby text explanation so the information is accessible without the image.

- **Source:** version Mermaid (`.mmd`) or uncompressed draw.io (`.drawio`) under `docs/diagrams/`. Prefer draw.io when people need visual editing. Reconcile human edits back to the source before regeneration; no two-way synchronizer is included.
- **draw.io generation:** use JGraph's official `drawio` skill if available, otherwise its current XML reference at [jgraph/drawio-mcp](https://github.com/jgraph/drawio-mcp). Use unique cell IDs, valid geometry, escaped XML, aligned nodes and correct relative coordinates for child elements. Follow the actual format/reference instead of assuming a fixed grid or banning valid XML features.
- **Confluence rendering:** a Mermaid code block is not a rendered diagram. Check the actual space's editor/app before publishing; draw.io for Jira and Confluence are distinct integrations. If available, upload the diagram and use the app's valid extension/macro from that site. Check attachment and extension revisions when updating: a successful upload can still display an older version.
- **Fallback:** export an image from the versioned source and include a source link plus text explanation. Ask before installing a new app or sending diagram contents to another service.
- **Read-back:** open the published page and inspect the rendered diagram. Connector success alone does not demonstrate rendering. If visual inspection is unavailable, report that limitation rather than declaring the page fully verified.

## Short technical projection

```text
Title: what this page describes
Source: <repository>/<path> @ <short commit>; updated <date>
Purpose: one or two sentences.
<rendered diagram or concise table>
Details: source link.
```

API: `Method | Path | Purpose | Authentication`, with details in the contract. Flow: one readable diagram and explanation; split when needed. Infrastructure: environments/services diagram plus `Component | Runtime location | Owner`.

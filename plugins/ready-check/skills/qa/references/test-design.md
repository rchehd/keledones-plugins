# Test design, oracles and investigation

Short reference for the `qa` skill. Apply only what the change and its RCs need.

## Risk

Rate every area the change touches: likelihood of a defect (size and complexity of the change, shared code,
past problems) × impact if it fails (data loss or disclosure, main flow blocked, wrong result, cosmetic).
Use H/M/L for each. High × high areas get required scenarios first; low × low areas may stay out of scope with
a stated reason. Pick regression scenarios from callers and shared paths of the changed code, not at random.

## Techniques

| Technique | Use when | How |
| --- | --- | --- |
| Equivalence partitioning | An input accepts classes of values | One value per class, including every invalid class (empty, wrong type, too long, forbidden characters) |
| Boundary values | A class has a minimum or maximum | The boundary and the value on each side, for example 499 / 500 / 501 characters |
| State transitions | The feature has states (draft, published, saved, cleared) | Every valid transition, plus at least one invalid one (repeat, back, double submit, action after delete) |
| Decision table | Several conditions combine (role × status × setting) | One case per combination that changes the outcome; collapse combinations that behave the same |
| Error guessing | Always, briefly | Use the profile's list of familiar problems and the history of this code |

Name the technique in each scenario so the plan shows why that value or path was chosen.

## Coverage categories

Use the expected outcome to select the primary category for a scenario.

| Category | What the scenario verifies |
| --- | --- |
| `accessibility` | A person can use the interface with a keyboard, assistive technology or other applicable accessibility criteria. |
| `user-flow` | A user completes a task and reaches the expected screen, data or state. |
| `access-control` | A role, permission or ownership rule allows or denies the action as intended. An expected denial can pass. |
| `error-handling` | Invalid input or a failure triggers the expected feedback, recovery or fallback. |

Keep the execution kind (such as `browser` or `api`) and the test technique in their own fields.
Omit the category if none of these describes the primary outcome.

## Oracles: how to decide that something is a bug

The RC's expected result comes first. Where the RC is silent, compare with (HICCUPPS):

- **History:** how the feature behaved before the change.
- **Image:** what the project or company would want to be seen doing.
- **Comparable products:** how similar features behave elsewhere.
- **Claims:** the task text, documentation, UI copy and messages.
- **Users' desires:** what a reasonable user expects.
- **Product:** consistency with the rest of this site (other forms, other pages).
- **Purpose:** what the feature is for.
- **Standards:** accessibility, HTTP, security and platform conventions.

Each finding names the oracle it relies on. When oracles disagree or only a weak one applies, ask the user
instead of guessing.

## Exploratory session

After the required scenarios, run one short session with a charter:

> Explore `<changed area>` with `<roles, data>` to discover `<risk>`.

Vary along SFDPOT where it fits the change: **S**tructure (components, cache, shared code), **F**unction (what it
does), **D**ata (values, sizes, languages), **P**latform (viewport, browser, JS off where relevant), **O**perations
(order of actions, back, refresh, two tabs), **T**ime (expiry, repeat, slow responses). Keep within the action
budget agreed in the plan. Record: what was covered, bugs, issues and open questions.

## Investigating a finding (RIMGEA)

1. **Replicate:** reproduce from a known state when safe.
2. **Isolate:** cut the steps to the minimum that still triggers it.
3. **Maximize:** find the worst realistic consequence.
4. **Generalize:** check whether the same defect appears in related places.
5. **Externalize:** say who is affected and why it matters.
6. **Report neutrally:** steps, expected, actual, evidence; no blame.

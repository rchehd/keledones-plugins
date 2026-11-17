# TypeScript review

Record actual TypeScript, Node.js, framework and affected dependency versions. Use the relevant rows:

| Change | Review |
| --- | --- |
| Public types or exports | Follow affected consumers, package exports and declaration compatibility. Check narrowing, nullability and the behavior callers rely on. |
| API or untrusted input | Trace runtime validation, authorization and output encoding. Confirm that type assertions at the boundary are backed by validation. |
| Async behavior | Check rejected promises, sequencing, cancellation and whether retries can repeat side effects. |
| Build or config | Check module resolution, generated inputs, build targets, project references and the lockfile. |
| UI | Check runtime state transitions, error and loading states, event cleanup and keyboard interaction. |

[TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html) ·
[Google code review guide](https://google.github.io/eng-practices/review/reviewer/looking-for.html)

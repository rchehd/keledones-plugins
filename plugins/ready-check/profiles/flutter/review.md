# Flutter review

Review each applicable area using the project's SDK version and architecture.

| Change | Review |
| --- | --- |
| Widget state, async work or subscriptions | Trace state ownership, rebuilds, stale responses and cleanup. Check controller and listener disposal, and context use after an asynchronous gap. |
| Navigation and app lifecycle | Check back navigation, deep links, restore/resume behavior and repeated actions. Apply the platform's expected behavior. |
| UI and accessibility | Check labels, semantics, focus, text scaling, and loading and error states. Use stable semantics identifiers for applicable device automation. |
| Storage, network or permissions | Trace sensitive data and the permission lifecycle. Select relevant OWASP MASVS controls for the affected paths. |
| Platform integration | Review supported OS versions, channel contracts and error handling on each affected target. |

[Flutter architecture](https://docs.flutter.dev/app-architecture) ·
[Accessibility testing](https://docs.flutter.dev/ui/accessibility/accessibility-testing) ·
[OWASP MASVS](https://mas.owasp.org/MASVS/)

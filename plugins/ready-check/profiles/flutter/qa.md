# Flutter QA

Use `flutter test --no-pub` with the project's prepared SDK for affected unit and widget behavior. Use the SDK
identified by `doctor` or the equivalent command from the project's SDK manager. Use existing
`integration_test` suites for app flows that they can exercise. For native system UI, device permissions or
cross-app behavior, use the project's device tests or Maestro flows on the approved target. Record the build
or revision, flavor, platform, device and OS, and evidence from the tested flow.

For Flutter Web, use Playwright on the actual web build. For native selectors, prefer user-facing
accessibility labels or stable `Semantics` identifiers supported by the project's SDK.

[Flutter integration testing](https://docs.flutter.dev/cookbook/testing/integration/introduction) ·
[Maestro Flutter support](https://docs.maestro.dev/get-started/supported-platform/flutter)

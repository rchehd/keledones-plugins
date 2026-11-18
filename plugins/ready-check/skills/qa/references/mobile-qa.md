# Native mobile QA

Use existing device tests first. Use Maestro flows for native UI or OS-level behavior within the approved
scenario. Playwright covers browser flows such as Flutter Web. Some changes need both.

1. Identify the app ID, build or commit, variant or flavor, test data, and expected result. Confirm the
   scenario's device, OS version and accessibility or permission state.
2. Use an already-provisioned Android device or emulator, or an iOS Simulator on macOS for Maestro. Use
   `adb devices` or `xcrun simctl list devices booted` to identify the target. Confirm that the intended
   app build is available. Missing required build, platform, tool or device evidence is `INCOMPLETE`.
3. Review the approved flow for fixture effects like permission changes or clearing app data. Use accessible
   labels or stable identifiers to select elements. On supported Flutter versions, expose identifiers
   through `Semantics`. Match the flow to the test data and initial app state.
4. Run `maestro --device <id> test <flow>` or the project's existing device test command. Compare the
   test result and observable UI or platform behavior with the expected outcome. Record evidence under
   the same QA case as the app build, device and OS identity, tool version, exit or report status, and
   relevant logs and screenshots. Use existing device scopes when running `flutter test integration_test -d <id>`.

For a changed mobile security boundary, check the relevant OWASP MASVS controls and the approved negative
case. For an approved design comparison, apply the [UI design checklist](../../review/references/ui-design.md)
to the actual device screenshot. Use a provisioned, authorized environment for any hosted device run.

[Maestro device selection](https://docs.maestro.dev/maestro-flows/flow-control-and-logic/specify-and-start-devices) ·
[Maestro Flutter support](https://docs.maestro.dev/get-started/supported-platform/flutter) ·
[Flutter integration testing](https://docs.flutter.dev/cookbook/testing/integration/introduction) ·
[OWASP MASVS](https://mas.owasp.org/MASVS/)

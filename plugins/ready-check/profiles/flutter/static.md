# Flutter static checks

The profile detects a Flutter SDK dependency under `dependencies.flutter` in `pubspec.yaml`. Select the
profile explicitly if the pubspec expresses the dependency indirectly, for example through YAML aliases.
The default runner is local. Each package uses its installed Flutter SDK, including FVM's prepared SDK when
present. Otherwise the local `FLUTTER_ROOT` or Flutter on the runner's `PATH` selects the SDK. Dart comes from the
same Flutter installation. On native Windows a prepared SDK supplies the Flutter tool snapshot and Dart
executable.

- `flutter analyze --no-pub` honors the project's analyzer configuration. When Dart code or
  analysis inputs change, the analyzer checks the package so it can catch affected consumers.
- `dart format --output=none --set-exit-if-changed` checks changed Dart files without rewriting them.
- The Git diff check reports whitespace errors and conflict markers within the selected scope.

Prepare the SDK and the app's package configuration with the project's usual setup steps. The profile
does not download an SDK or resolve dependencies. Use the same selected SDK for `flutter test --no-pub`
when the task calls for unit or widget tests. Run existing device-level `integration_test` suites in an
approved test environment. Record test outcomes in QA and follow the project's usual generated file and
build output setup.

[Flutter CLI](https://docs.flutter.dev/reference/flutter-cli) ·
[Dart format](https://dart.dev/tools/dart-format) ·
[Flutter testing](https://docs.flutter.dev/testing/overview)

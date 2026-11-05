# iOS setup

Manual steps the human does in Xcode before /skeleton. Walk them through one step at a time and
wait for "done" before the next. Fill in the app's name from the memo wherever it says <App>.
After the last step, `ios-pipeline stack check` must show all ✅.

1. **Create the project.** Xcode › File › New › Project › iOS › App. Product Name: <App>.
   Interface: SwiftUI. Testing System: **Swift Testing with XCUITests** (so unit and UI test
   targets exist). Save it inside the app folder's `App/` folder. In the save dialog, **uncheck
   "Create Git repository on my Mac"**: the app folder's repo is the only one.
2. **Swift 6.** In Build Settings for the app target and the unit test target, set
   **Swift Language Version = Swift 6**.
3. **Actor isolation.** If Build Settings shows **Default Actor Isolation**, set it to
   **nonisolated** for the app and unit test targets. Xcode 26 defaults new apps to MainActor,
   which would make every type main-actor bound.
4. **Minimum iOS.** Set the deployment target to the memo's minimum iOS version.
5. **Capabilities** (only those the memo needs, e.g. iCloud, Push Notifications, Background Modes):
   Signing & Capabilities › + Capability. Choose the human's development team for signing.
6. **Config.** Fill in `.pipeline/config.sh` with the names Xcode used, e.g. for an app named Tally:
   `APP_PROJECT="App/Tally/Tally.xcodeproj"`, `APP_SCHEME="Tally"`, `APP_MODULE="Tally"`,
   `APP_SOURCE_DIR="App/Tally/Tally"`, `APP_TEST_DIR="App/Tally/TallyTests"`,
   `UNIT_TEST_TARGET="TallyTests"`, `UI_TEST_TARGET="TallyUITests"`. You may edit this file for
   the human once they confirm the names.

Notes for the human:
- New projects use synchronized folders, so files the pipeline adds join their target
  automatically; no project-file edits are needed.
- Commit from Xcode only when the pipeline is idle; Xcode commits bypass the merge guard.

## For a feature
A feature that needs a new capability, entitlement, Info.plist usage description (camera, location,
notifications…) or a new target (widget, watch app, extension) needs the matching manual step in
Xcode. Walk the human through only those steps, then rerun `ios-pipeline stack check`.

## For an adoption
The Xcode project already exists; `ios-pipeline stack detect --apply ios` has filled in
`.pipeline/config.sh`. Walk the human through only the steps `ios-pipeline stack check` or the
detection report still shows, one at a time:

1. **Synchronized folders.** In Xcode's Project navigator, right-click each top-level group that holds
   the app's or the tests' Swift files › **Convert to Folder**. Xcode may say a group can't be
   converted (files outside the folder, or a group without a folder): resolve what it names, then
   retry. Build once (⌘B) to confirm nothing moved.
2. **Test targets.** If there is no unit test target: File › New › Target › **Unit Testing Bundle**,
   Testing System **Swift Testing**, target to be tested: the app. If there is no UI test target:
   File › New › Target › **UI Testing Bundle**. Then set `UNIT_TEST_TARGET`, `APP_TEST_DIR` and
   `UI_TEST_TARGET` in `.pipeline/config.sh` (you may do that for the human).
3. **Shared scheme.** Product › Scheme › Manage Schemes…, tick **Shared** for the app's scheme, and
   make sure its Test action includes both test targets.
4. **Actor isolation.** If Build Settings shows **Default Actor Isolation = MainActor**, set it to
   **nonisolated** for the app and unit test targets. Legacy code may show new warnings; they are not
   gated during the adoption.
5. **Leave the Swift Language Version as it is.** It switches to Swift 6 in the adoption's Stage 6.
6. Commit with the human's go-ahead (`chore: adopt setup`): the converted project file and the new
   targets.

## Final switch (adoption Stage 6)
Every module is adopted, so nothing legacy is left to hold the project back. In Build Settings for the
app target and the unit and UI test targets, set **Swift Language Version = Swift 6**. Then
`ios-pipeline stack check` (now the normal check) and `ios-pipeline gates --all`, which build with
warnings as errors again. Fixes go to the modules that own the files (or to the app shell's unit).

# iOS stack: setup

These are the manual steps the human does in Xcode before `/bull:skeleton`. Walk the human through
them one step at a time, and wait for "done" before the next. Replace `<App>` with the app's name
from the memo. When every step is done, `bull stack check` must show every item ✅.

1. **Create the project.** Choose `Xcode › File › New › Project › iOS › App`. Set Product Name to
   `<App>`, Interface to SwiftUI, Language to Swift, and Testing System to
   **Swift Testing with XCUITests**: the option that also creates the UI test target, so both the
   unit and UI test targets exist (`<App>UITests` must exist afterwards). Save it in the app
   folder's `App/` folder. **Uncheck "Create Git repository on my Mac"**: the app folder's repo is
   the only one, and `bull stack check` fails on a nested repo.
2. **Swift 6.** In Build Settings, for the app target and the unit test target, set **Swift
   Language Version** (`SWIFT_VERSION`; newer Xcode may label it "Swift Language Mode") to
   **Swift 6**.
3. **Actor isolation.** If Build Settings shows **Default Actor Isolation**
   (`SWIFT_DEFAULT_ACTOR_ISOLATION`), set it to **nonisolated** for the app and unit test targets.
   Xcode 26 makes new apps default to MainActor, which would bind every type to the main actor.
4. **Minimum iOS.** Set the deployment target of every target to the memo's minimum iOS version.
5. **Capabilities.** Add each capability the memo needs (iCloud, Push Notifications, Background
   Modes…) in `Signing & Capabilities › + Capability`. Choose the human's development team for
   signing.
6. **Shared scheme.** Open `Product › Scheme › Manage Schemes…` and tick **Shared** for the app's
   scheme, so it is in git. Check that its Test action includes both test targets.
7. **Lint configs.** Write `.swiftlint.yml` and `.swift-format` at the part root, with the contents
   of the stack's `lint/swiftlint.yml` and `lint/swift-format.json`. You may write them for the
   human. The human may edit them later.

   `.swiftlint.yml`:
   ```yaml
   disabled_rules:
     - trailing_comma        # swift-format adds trailing commas
     - todo
   opt_in_rules:
     - force_unwrapping
     - implicitly_unwrapped_optional   # IBOutlets stay allowed (the rule's default mode)
     - empty_count
     - first_where
     - contains_over_first_not_nil
     - redundant_nil_coalescing
   line_length:
     warning: 120
     ignores_comments: true
   identifier_name:
     min_length: 1
     excluded: [id, x, y]
   ```

   `.swift-format`:
   ```json
   {
     "version": 1,
     "lineLength": 120,
     "indentation": { "spaces": 4 },
     "maximumBlankLines": 1,
     "respectsExistingLineBreaks": true,
     "lineBreakBeforeEachArgument": false,
     "rules": { "AlwaysUseLowerCamelCase": false, "NeverForceUnwrap": true, "NeverUseForceTry": true }
   }
   ```
8. **Settings.** Set them with the names Xcode used. For an app named Tally:
   ```
   bull config set project App/Tally/Tally.xcodeproj
   bull config set scheme Tally
   bull config set source_dir App/Tally/Tally
   bull config set test_dir App/Tally/TallyTests
   bull config set ui_test_dir App/Tally/TallyUITests
   bull config set unit_test_target TallyTests
   bull config set ui_test_target TallyUITests
   ```
   Optionally run `bull config set simulator "<device name>"`; by default the gates use the
   newest available iPhone. You may run these once the human confirms the names.
9. **Commit and check.** Commit the project; `git status` must show no `xcuserdata/`. Then run
   `bull stack check`. It checks that Xcode is present, the project and scheme exist, the targets
   use Swift 6, the test targets include their folders, the folders are synchronized, and there are
   no nested git repos.

Notes for the human:
- New projects use synchronized folders, so files bull's agents add join their target with no
  project-file edits.
- Commit from Xcode only while no agent is working: Xcode commits bypass bull's merge guard.
- `bull stack run prune` frees the build folder when it grows.

## For a feature

A feature that needs a new capability, entitlement, `Info.plist` usage description (camera,
location, notifications…) or a new target (widget, watch app, extension) needs the matching manual
step in Xcode. Walk the human through only those steps, then rerun `bull stack check`.

## For an adoption

The Xcode project exists, and `bull stack detect --apply` has filled in the settings. Walk the
human through only what `bull stack check` or the detection report still shows, one step at a time:

1. **Synchronized folders.** In the Project navigator, right-click each top-level group that holds
   the app's or the tests' Swift files and choose **Convert to Folder**. If Xcode says a group can't
   be converted (files outside the folder, a group without a folder), resolve what it names and
   retry. Build once (⌘B) to confirm nothing moved.
2. **Test targets.** If there is no unit test target, add one with
   `File › New › Target › Unit Testing Bundle`: Testing System Swift Testing, target to be tested
   the app. If there is no UI test target, add one with `File › New › Target › UI Testing Bundle`.
   Then set `unit_test_target`, `test_dir`, `ui_test_target` and `ui_test_dir` with
   `bull config set` (you may).
3. **Shared scheme.** As in step 6 above: tick **Shared**, with both test targets in its Test
   action.
4. **Actor isolation.** Change Default Actor Isolation (`SWIFT_DEFAULT_ACTOR_ISOLATION`) from
   MainActor to **nonisolated** for the app and unit test targets. Legacy code may show new
   warnings; they aren't gated during the adoption.
5. **Leave the Swift Language Version as it is.** That setting (`SWIFT_VERSION`; newer Xcode may
   label it "Swift Language Mode") switches to Swift 6 at the final switch.
6. **Lint configs.** Keep the app's own `.swiftlint.yml` and `.swift-format` if it has them;
   otherwise write them as in step 7 above. During the adoption they only apply to `Modules/` and
   the module test folders.
7. **Commit** with the human's go-ahead (`chore: adopt setup`): the converted project file and any
   new targets. Then run `bull stack check`; it accepts Swift 5 while the adoption is active.

## Final switch

Every module is adopted, so nothing legacy holds the project back. In Build Settings, for the app,
unit test and UI test targets, set **Swift Language Version** (`SWIFT_VERSION`; newer Xcode may
label it "Swift Language Mode") to **Swift 6**. Then run `bull stack check` (now the normal check)
and `bull gates --all`, which build with warnings as errors again. Fixes go to the modules that own
the files, or to the app shell's unit.

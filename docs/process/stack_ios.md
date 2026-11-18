# stack_ios: source note

The content of the `ios` stack's Markdown (`rules.md`, `setup.md`, the fixture's `SETUP.md` and
outline), its lint configs and its fixture app, rewritten from v1's `stacks/ios/` and the iOS parts
of v1's `docs/adopt.md` (memo **v1 Markdown review**) in `bull` terms and v2 formats. The memo's
`stack_ios` section says *what* the module is; this note says *what each file says*. test-writer and
code-writer read this note, never the v1 files. Approved by the human like a memo section; changes
after approval go through the decisions log.

How to read it: §1 holds the rules every file follows. §2–§6 give each file's content, section by
section, in the order the file should have them. Wording is the code-writer's; every rule, step and
check listed here must be in the file, and nothing in §1.3 may be. §7 lists the choices this note
makes where v1 and the memo leave a gap.

Style: plain words, short sentences, second person to the agent in `rules.md` ("You …"),
imperative steps in `setup.md` and `SETUP.md`. Commands, paths, settings and Xcode menu paths in
backticks or bold as v1 did (`Xcode › File › New › Project`). No emoji except the ✅/✗ that `bull
stack check` itself prints.

## 1. Rules for every file

### 1.1 Names
| v1 | v2 |
| --- | --- |
| `ios-pipeline <cmd>` | `bull <cmd>` |
| `ios-pipeline stack test ios` | `bull stack test ios` |
| `ios-pipeline stack rules <agent>` | `bull stack rules <agent>` |
| `ios-pipeline stack detect --apply ios` | `bull stack detect --apply` |
| `ios-pipeline template outline` | `bull template outline` |
| `gates <Module> --fast`, `--failed` | `bull gates <Module> --fast`, `bull gates --failed` |
| ui-test-writer, UI tests (as the agent's job) | journey-test-writer, journey tests (XCUITest is still the tool) |
| `.pipeline/config.sh` | `.bull/config.toml` (`bull config set <key> <value>`) |
| `APP_PROJECT`, `APP_SCHEME` | the `project`, `scheme` settings |
| `APP_SOURCE_DIR`, `APP_TEST_DIR` | the `source_dir`, `test_dir` settings |
| `UNIT_TEST_TARGET`, `UI_TEST_TARGET` | the `unit_test_target`, `ui_test_target` settings |
| the UI test target's folder | the `ui_test_dir` setting |
| `APP_MODULE` | the app's module name (§7.3) |
| `ADOPT_MODE`, `ADOPTING` | "while an adoption is active" (bull sets `BULL_ADOPT_MODE`) |
| `stacks/ios/owned_warnings.py` | the build gate (no file name in the text) |
| `stacks/ios/fixture/project/App` | `src/bull/Modules/stack_ios/ios/fixture/project/App` (in bull's repo) |
| "the pipeline" (the tool) | bull |
| `### <Module>`, `MAX_FILES_PER_UNIT` | `### <Module>`, `max_files_per_unit` |

Module names stay capitalized in this stack (`Counter`, `Modules/Counter/`), as Swift type names
are; `Modules/`, `Contracts/`, `Mocks/` and `Views/` are capitalized too.

### 1.2 Stack words are allowed
These files are stack-specific: Xcode, Swift, SwiftUI, UIKit, iOS, iPhone, simulator, XCUITest,
`xcodebuild` and Swift terms are fine here (the banned-word list applies to bull's stack-neutral
text, not to a stack's own files).

### 1.3 Never in any file
`ios-pipeline`, `.pipeline/`, `config.sh`, `stack.sh`, `gates.sh`, `owned_warnings.py`,
`ui-test-writer`, `APP_` or `UNIT_TEST_TARGET`-style variable names, any v1 build checklist, any
absolute path, and "the pipeline" meaning the tool.

### 1.4 What the text relies on in `stack.toml`
The code-writer of `stack.toml` (unit 2) and of the Markdown (unit 5) keep these in step:
- `kind = "app"`, `source_glob = "*.swift"`, `test_glob = ["*Tests.swift"]`, `comment = "//"`,
  `scaffold = ["App"]`, `gitignore = ["xcuserdata/", "*.xcuserstate", ".DS_Store"]`.
- `agents`: `skeleton-builder`, `screen-builder`, `test-writer`, `code-writer`, `reviewer`,
  `coverage-analyst`, `journey-test-writer`, `surveyor` (rules.md has one section for each).
- `[[stack.requires]]`: `xcodebuild` (hint: install Xcode 26 or later from the App Store, open it
  once, then `xcode-select -s /Applications/Xcode.app`) and `swiftlint` (hint: `brew install
  swiftlint`). `swift-format` ships with Xcode (`xcrun swift-format`).
- `[gates] journeys` set; no `[run]`, no `[interfaces]`; `[commands] prune`.
- Settings defaults: `project` `App/MyApp/MyApp.xcodeproj`, `scheme` `MyApp`, `source_dir`
  `App/MyApp/MyApp`, `test_dir` `App/MyApp/MyAppTests`, `ui_test_dir` `App/MyApp/MyAppUITests`,
  `unit_test_target` `MyAppTests`, `ui_test_target` `MyAppUITests`, `simulator` empty (newest
  iPhone), `coverage.exclude` `["*/Views/*", "*/Mocks/*"]` (§7.5).

## 2. rules.md

Title `# iOS stack: rules`. One line under it: `bull stack rules <agent>` prints `## common` plus
the agent's section; `bull stack rules outline` prints `## outline` only. Sections in this order:
`## common`, `## outline`, `## skeleton-builder`, `## screen-builder`, `## test-writer`,
`## code-writer`, `## reviewer`, `## coverage-analyst`, `## journey-test-writer`, `## surveyor`.

### 2.1 common
- Swift 6 with strict concurrency; SwiftUI for new UI. File names end in `.swift`, named after the
  main type they hold.
- Layout: the app's source folder is `<source_dir>`; modules are folders at
  `<source_dir>/Modules/<Module>/` with `Contracts/` (what `bull api` reads), `Mocks/`, `Views/` and
  the implementation files. Unit tests: `<test_dir>/<Module>/<File>Tests.swift`. Journey tests:
  `<ui_test_dir>/JourneyTests.swift`.
- The whole app compiles as **one Swift module**: every type name must be unique across modules,
  and access is `internal` by default. The compiler doesn't enforce module boundaries: a file may
  use another module's `Contracts/` types only, and only from modules its memo entry lists under
  `Depends on`. Review checks it.
- Naming follows the Swift API Design Guidelines.
- Tests: Swift Testing (`import Testing`, `@testable import <AppModule>`, `@Test`, `#expect`,
  `#require`). `<AppModule>` is the app target's module name: the `scheme` setting, unless the
  app target's `PRODUCT_MODULE_NAME` build setting says otherwise (§7.3).
- Journey tests: XCTest / XCUITest in the UI test target.
- No force unwraps and no `try!` anywhere (one exception for UIKit outlets, under code-writer).
- Never edit the `.pbxproj` file: Xcode's synchronized folders add new files to their target.
- Lint is SwiftLint (`swiftlint lint --strict`) and swift-format (`xcrun swift-format lint
  --strict`) on the module's source and test folders, with the app's `.swiftlint.yml` and
  `.swift-format` at the part root (setup writes them; §3 step 7), else the stack's own.
- Build output and result bundles live under the app's `.bull/` (never the global DerivedData);
  `bull stack run prune` deletes them when they grow.
- Adoption terms bull's generic instructions use: the **clean-state launch option** is the
  `-uiTesting` launch argument; the **composition root** is `AppDependencies.swift` in the app
  shell; the **final switch** (adoption stage 6) moves every target to Swift 6 language mode; a
  screen's **UI technology** is `UI: UIKit` or `UI: SwiftUI`.
- Adopted apps keep their UIKit screens (UIKit, storyboards, xibs): the memo marks each screen
  `UI: UIKit` or `UI: SwiftUI`. A UIKit screen's logic lives in a tested view model; its view
  controller is a thin view in `Views/` (left out of coverage, covered by the journey tests).
- While an adoption is active the project may still be in Swift 5 mode, but code in `Modules/` and
  module test folders must compile without warnings under Swift 6 rules: the build gate fails on
  any warning there, and ignores warnings in legacy code.

### 2.2 outline
- Protocols in the memo are Swift, fenced ```` ```swift ````, conforming to `Sendable`.
- Data models are `struct`, `Sendable`, `Codable`, `Equatable`, `Hashable` unless the memo entry
  says why not.
- `Files:` lines use paths relative to the module folder, e.g. `Contracts/CounterStore.swift,
  Contracts/Counter.swift | FileCounterStore.swift`.
- UI: views in `Views/<Screen>View.swift`; view models next to the module's other files as
  `<Screen>ViewModel.swift`. Each screen under "Screens and navigation" names its module.
- `## Constraints` names the minimum iOS version and any capability the app needs (iCloud, push
  notifications, background modes…): setup turns them into Xcode steps.
- The app shell (the `@main` entry point, `AppDependencies.swift`, assets, `Info.plist`,
  entitlements, launch screen) is not a module.
- Adoption memo (extra lines; `bull template outline` shows them):
  - `## Legacy code` with `- App shell: <paths relative to source_dir>` (the files above); `- App
    shell tests: <paths relative to test_dir>` (the shell's own tests, the test folder's
    `.swiftlint.yml`, a `.storekit` configuration the scheme points at: these are not old tests);
    `- Legacy folders:` and `- Renames: Foo → LegacyFoo, …` as bull's template shows.
  - Per module: `- Legacy files:` (a file split across modules is listed in each, with `(part:
    <what>)`), `- Legacy tests:`, `- Callers to repoint:` (`none` if none).
  - Per screen: `UI: UIKit` or `UI: SwiftUI`. A UIKit screen's files are
    `Views/<Screen>ViewController.swift` (plus its storyboard or xib, if any) and
    `<Screen>ViewModel.swift`.

### 2.3 skeleton-builder
- Models in `Contracts/`, exactly as the memo's Data models; `struct`, `Sendable`, `Codable`,
  `Equatable`, `Hashable` unless the memo says otherwise. Protocols in `Contracts/` exactly as
  drafted.
- Stubs call `fatalError("Not implemented: <Type>.<method>")`; in feature mode
  `fatalError("Not implemented: <Type>.<method> (feature <slug>)")`.
- Mocks: `Mock<Protocol>` types in `Mocks/`, returning realistic sample data and recording calls.
- One placeholder test file per implementation file: a top-level `@Suite struct <File>Tests` with
  one `@Test func placeholder() {}`.
- The app's root view may show a placeholder.
- Declaration-only files get `// coverage-exempt-file: declarations only` as their first line after
  the imports (within the first 10 lines). Xcode records no coverage for a file without executable
  code, so without the marker the coverage gate fails it. Declaration-only means: protocols with
  only requirements, enums with plain cases (no methods, computed properties or raw-value logic),
  structs with only stored properties and synthesized conformances, `static let` constants.
  Anything with a method body, computed property, initializer body or default argument expression
  is not declaration-only: no marker.
- If the unit test target, the shared scheme or Swift 6 mode is missing (the setup gate or `bull
  stack check` says so), don't fix the project: list the exact Xcode steps under `MANUAL STEPS FOR
  HUMAN` (`bull stack setup` has them).
- Adopt mode renames: a clashing legacy type `Foo` becomes `LegacyFoo` (and its file, if named
  after it). Take care with `@objc` names, storyboard and xib references (`customClass="Foo"`),
  `NSStringFromClass`, `Codable` keys and persisted type names: a rename must not change what is
  stored or what Interface Builder loads; keep the old runtime name with `@objc(Foo)` where needed.
- Adopt mode scaffold: an empty `AppDependencies.swift` composition root in the app shell, where
  the memo's `## Legacy code` puts it.

### 2.4 screen-builder
- The view goes in `<source_dir>/Modules/<Module>/Views/<Screen>View.swift`; the view model in
  `<source_dir>/Modules/<Module>/<Screen>ViewModel.swift`: `@MainActor`, `@Observable`, depending
  only on the protocols passed to its initializer.
- SwiftUI previews (`#Preview`) use the module's `Mock…` types.
- Accessibility: every interactive element has an accessibility label; support Dynamic Type (no
  fixed font sizes); works in dark mode.
- Test identifiers: `.accessibilityIdentifier("<screen>.<element>")` on every element a journey
  touches (e.g. `counterList.addButton`).
- Adopt mode (`MODE: adopt-identifiers`): SwiftUI views get `.accessibilityIdentifier(...)`; UIKit
  views get `accessibilityIdentifier` set in code (in `viewDidLoad` or where the view is built) or
  in Interface Builder's Identity inspector for storyboard elements. Same names.

### 2.5 test-writer
- Put each file's tests in a top-level suite named `<File>Tests` (`@Suite struct <File>Tests`).
  More suites per file are fine. `bull gates <Module> --fast` runs every **top-level** `struct`,
  `class` or `actor` in the module's test folder whose name ends in `Tests` (or that carries
  `@Suite`), whatever the file is called; nested suites run with their parent. Always end suite
  names in `Tests`.
- Parameterized tests (`@Test(arguments:)`) for input tables.
- Name tests by behavior: `@Test("Deleting a missing counter throws notFound")`.
- A unique temporary directory per test (`FileManager.default.temporaryDirectory` plus a UUID),
  removed afterwards.
- Before you report, from the part root: `xcrun swift-format format -i <your test files>`, then
  `swiftlint lint --fix <files>` and `swiftlint lint --strict <files>`; fix what is left.

### 2.6 code-writer
- Swift 6 strict concurrency: no data races, no `@unchecked Sendable`, no `nonisolated(unsafe)`.
  UI-facing types are `@MainActor`.
- Errors: throw typed, documented errors. No `fatalError` except for genuinely unreachable states.
- Secrets in the Keychain only; never in `UserDefaults` or logs.
- No retain cycles in closures (`[weak self]` where needed); release observers, timers and file
  handles.
- Implementation details are `private` or `fileprivate` unless another file in the module needs
  them.
- Doc comments (`///`) on every non-private declaration in `Contracts/`, and on tricky logic.
- Iterate with `bull gates --failed`, then confirm with `bull gates <Module> --fast`.
- UIKit screens (adopted apps): the view controller is `@MainActor`, holds no business logic (it
  binds the view model's state to views and forwards actions), and lives in `Views/`. `@IBOutlet
  private weak var name: UIType!` is the one allowed implicitly unwrapped declaration. Observe the
  view model with Observation (`withObservationTracking`, or `UIObservationTrackingEnabled` on iOS
  18+) or Combine; cancel subscriptions on deinit.
- The view model is `@MainActor`, `@Observable` (or `ObservableObject` if the minimum iOS is below
  17), testable without UIKit, and depends only on contracts.
- Adoption: `AppDependencies` (app shell) creates every live implementation once and passes it on;
  no new singletons or `static let shared`.

### 2.7 reviewer
- Error handling: no force unwraps or `try!`; nothing swallowed with `try?` unless the spec allows
  it.
- Security: secrets only in the Keychain, never in logs or `UserDefaults`; HTTPS only (no ATS
  exceptions); file protection set on stored files; only the permissions and usage descriptions
  needed.
- Concurrency: UI work on the main actor; no data races, `@unchecked Sendable` or
  `nonisolated(unsafe)`; tasks cancel cleanly; no retain cycles; observers and timers released.
- API design: Swift API Design Guidelines.
- Whole app (`SCOPE: whole app`): accessibility labels, Dynamic Type, dark mode, and no heavy work
  on the main thread at launch.
- Style nits SwiftLint or swift-format would catch are not findings.
- A `// coverage-exempt-file:` marker is valid only on a declaration-only file (§2.3). A method
  body, computed property, initializer body or default argument expression in a marked file is a
  blocker: the marker goes, the code needs tests.
- Cross-module use goes through `Contracts/` of declared dependencies only (§2.1).
- UIKit (adopted apps): view controllers are thin, as the code-writer rules say. Outlets other
  than `@IBOutlet private weak var x: T!`, logic in a view controller, or a singleton introduced
  during an adoption is a blocker.

### 2.8 coverage-analyst
- Markers are Swift line comments: `// coverage-exempt: <reason>` at the end of the line, or
  `// coverage-exempt-begin: <reason>` … `// coverage-exempt-end` around a block.
- A file under "Files without coverage data" has no executable code or never ran. Declaration-only
  (§2.3): add `// coverage-exempt-file: declarations only` after its imports. Otherwise `missed`.
- Typically infeasible: system callbacks (app delegate, notification handlers), an unreachable
  `fatalError`, OS failures that can't be simulated.
- `Views/` and `Mocks/` are already outside coverage; don't mark them.

### 2.9 journey-test-writer
- One test method per journey in `<ui_test_dir>/JourneyTests.swift` (`final class JourneyTests:
  XCTestCase`), named after the journey: `testJourney1_AddFirstCounter()`.
- Find elements by `accessibilityIdentifier` (`<screen>.<element>`). If one is missing, return
  `blocked` naming the screen that needs it; don't add identifiers yourself.
- Launch with `app.launchArguments = ["-uiTesting"]`: the app uses that argument to start from a
  clean, in-memory state. If the app doesn't support it yet, return `blocked`.
- Wait for elements (`waitForExistence(timeout:)`), never `sleep`.
- A journey that reaches a service part: bull passes its address to the test runner as
  `BULL_URL_<PART>`; read it from `ProcessInfo.processInfo.environment` and hand it to the app in
  `app.launchEnvironment`. If it is missing, fail with a message naming the variable (§7.6).
- Adopt mode (`MODE: adopt-baseline`): put `JourneyTests.swift` in the UI test target's existing
  folder; leave any old UI tests alone.

### 2.10 surveyor
- UI technology per screen: SwiftUI (`View` structs), UIKit in code (`UIViewController` subclasses
  building views), or Interface Builder (storyboard scenes, xibs: list the file and scene).
- Navigation: `NavigationStack`/`NavigationLink`, `UINavigationController` pushes, modal
  presentations, segues (storyboard identifiers), tab bars, coordinators.
- Singletons and globals: `static let shared`, global `let`/`var`, `UserDefaults.standard`,
  `NotificationCenter.default`, `AppDelegate`/`SceneDelegate` state.
- Persistence: Core Data (`.xcdatamodeld`), SwiftData (`@Model`), files, `UserDefaults`, Keychain.
- Concurrency today: completion handlers, `DispatchQueue`, `async`/`await`, actors, `@MainActor`.
- You may open a file outside your list only to follow a type a listed file uses, and only its
  declaration.

## 3. setup.md

Title `# iOS stack: setup`. Intro: manual steps the human does in Xcode before `/bull:skeleton`;
walk them through one step at a time and wait for "done" before the next; replace `<App>` with
the app's name from the memo; afterwards `bull stack check` must show every item ✅. Steps:

1. **Create the project.** `Xcode › File › New › Project › iOS › App`. Product Name `<App>`;
   Interface SwiftUI; Language Swift; Testing System **Swift Testing with XCUITests** (so the unit
   and UI test targets exist). Save it in the app folder's `App/` folder, and **uncheck "Create
   Git repository on my Mac"**: the app folder's repo is the only one (`bull stack check` fails on
   a nested repo).
2. **Swift 6.** Build Settings, for the app target and the unit test target: **Swift Language
   Version = Swift 6**.
3. **Actor isolation.** If Build Settings shows **Default Actor Isolation**, set it to
   **nonisolated** for the app and unit test targets (Xcode 26 defaults new apps to MainActor,
   which would make every type main-actor bound).
4. **Minimum iOS.** The deployment target is the memo's minimum iOS version, for every target.
5. **Capabilities** the memo needs (iCloud, Push Notifications, Background Modes…): `Signing &
   Capabilities › + Capability`. Choose the human's development team for signing.
6. **Shared scheme.** `Product › Scheme › Manage Schemes…`, tick **Shared** for the app's scheme
   (so it is in git), and check its Test action includes both test targets (§7.4).
7. **Lint configs.** Write `.swiftlint.yml` and `.swift-format` at the part root with the contents
   of the stack's `lint/swiftlint.yml` and `lint/swift-format.json` (shown in full in this step;
   the human may edit them later). The agent may write them for the human.
8. **Settings.** With the names Xcode used, e.g. for an app named Tally: `bull config set project
   App/Tally/Tally.xcodeproj`, `scheme Tally`, `source_dir App/Tally/Tally`, `test_dir
   App/Tally/TallyTests`, `ui_test_dir App/Tally/TallyUITests`, `unit_test_target TallyTests`,
   `ui_test_target TallyUITests`. Optionally `simulator "<device name>"` (default: the newest
   available iPhone). The agent may run these once the human confirms the names.
9. **Commit** the project (`git status` shows no `xcuserdata/`), then `bull stack check`: Xcode
   present, project and scheme exist, Swift 6, test targets include their folders, synchronized
   folders, no nested git repos.

Notes for the human: new projects use synchronized folders, so files bull's agents add join their
target with no project-file edits. Commit from Xcode only while no agent is working (Xcode commits
bypass bull's merge guard). `bull stack run prune` frees the build folder when it grows.

`## For a feature`: a feature that needs a new capability, entitlement, `Info.plist` usage
description (camera, location, notifications…) or a new target (widget, watch app, extension)
needs the matching manual step in Xcode. Walk the human through only those steps, then rerun
`bull stack check`.

`## For an adoption`: the Xcode project exists; `bull stack detect --apply` has filled in the
settings. Walk the human through only what `bull stack check` or the detection report still shows,
one at a time:
1. **Synchronized folders.** In the Project navigator, right-click each top-level group holding the
   app's or the tests' Swift files › **Convert to Folder**. If Xcode says a group can't be converted
   (files outside the folder, a group without a folder), resolve what it names and retry. Build
   once (⌘B) to confirm nothing moved.
2. **Test targets.** No unit test target: `File › New › Target › Unit Testing Bundle`, Testing
   System Swift Testing, target to be tested: the app. No UI test target: `File › New › Target › UI
   Testing Bundle`. Then set `unit_test_target`, `test_dir`, `ui_test_target`, `ui_test_dir` (the
   agent may).
3. **Shared scheme**, as step 6 above, with both test targets in its Test action.
4. **Actor isolation**: Default Actor Isolation = MainActor → **nonisolated** for the app and unit
   test targets. Legacy code may show new warnings; they aren't gated during the adoption.
5. **Leave the Swift Language Version as it is.** It switches to Swift 6 at the final switch.
6. **Lint configs**: keep the app's own `.swiftlint.yml`/`.swift-format` if it has them; otherwise
   as step 7 above. They only apply to `Modules/` and module tests during the adoption.
7. Commit with the human's go-ahead (`chore: adopt setup`): the converted project file and the new
   targets. Then `bull stack check` (it accepts Swift 5 while the adoption is active).

`## Final switch`: every module is adopted, so nothing legacy holds the project back. In Build
Settings for the app, unit test and UI test targets set **Swift Language Version = Swift 6**. Then
`bull stack check` (now the normal check) and `bull gates --all`, which build with warnings as
errors again. Fixes go to the modules that own the files (or to the app shell's unit).

## 4. Lint configs

### 4.1 lint/swiftlint.yml
```yaml
# The ios stack's SwiftLint defaults (an app's own .swiftlint.yml replaces this file).
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
`force_try` and `force_cast` are on by default; `--strict` turns every warning into a failure.

### 4.2 lint/swift-format.json
swift-format's defaults with Xcode's indentation and a line length matching SwiftLint's:
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
(`AlwaysUseLowerCamelCase` off: SwiftLint's `identifier_name` already covers naming, and
Swift Testing's `@Test("…")` functions are named freely.)

## 5. Fixture: SETUP.md and outline

### 5.1 fixture/SETUP.md
Title `# iOS fixture: the Xcode project (once, by hand)`. Intro: `bull stack test ios` runs the
iOS gates against this fixture. The Swift files, the memo and the cases are in the repo; the Xcode
project is made in Xcode once, on a Mac with Xcode 26 or later. Until it exists every case reports
"not run". About ten minutes. Paths are relative to bull's repo. Steps as v1, renamed:

1. `mkdir -p src/bull/Modules/stack_ios/ios/fixture/project/App`.
2. **Create the project.** `Xcode › File › New › Project › iOS › App`: Product Name **Fixture**
   (the cases use this name); Team None; Organization Identifier anything (e.g. `dev.bull`);
   Interface SwiftUI; Language Swift; Testing System **Swift Testing with XCUITests**; Storage None.
   Save in `…/fixture/project/App/`, **uncheck "Create Git repository on my Mac"**.
3. **Swift 6** for Fixture, FixtureTests and FixtureUITests.
4. **Actor isolation**: Default Actor Isolation → **nonisolated** for Fixture and FixtureTests.
5. **Minimum iOS 18.0** for every target, so the fixture runs on more simulators.
6. **Shared scheme**: tick **Shared** for Fixture (the cases need
   `Fixture.xcodeproj/xcshareddata/xcschemes/Fixture.xcscheme`).
7. **Remove the template's tests, outside Xcode** (quit Xcode first): delete
   `FixtureTests/FixtureTests.swift`, `FixtureUITests/FixtureUITests.swift`,
   `FixtureUITests/FixtureUITestsLaunchTests.swift`; `touch` a `.gitkeep` in both folders. Keep
   `FixtureApp.swift`, `ContentView.swift`, `Assets.xcassets`. Why not in Xcode: deleting a folder's
   last file there removes the folder and its link to the target, so no test runs.
8. `bull stack test ios`: every case ✅. If one isn't: `bull stack test ios --case <id>` and read
   its expected/got lines.
9. Commit `…/fixture/project/App` (no `xcuserdata/`, no `DerivedData/`).

`## If the template's tests were deleted in Xcode`: v1's repair (recreate both folders with
`.gitkeep`; drag each onto the project choosing **Create folders** and ticking only its own target;
quit Xcode; `grep -c PBXFileSystemSynchronizedRootGroup …/project.pbxproj` prints 5, a broken
project 3).

### 5.2 Fixture layout
Four folders, so redoing the Xcode project never touches the Swift files (§7.7). `cases.json`:
```json
"layout": {
  "project/": ".",
  "app/": "App/Fixture/Fixture/",
  "tests/": "App/Fixture/FixtureTests/",
  "ui-tests/": "App/Fixture/FixtureUITests/"
},
"settings": {
  "project": "App/Fixture/Fixture.xcodeproj", "scheme": "Fixture",
  "source_dir": "App/Fixture/Fixture", "test_dir": "App/Fixture/FixtureTests",
  "ui_test_dir": "App/Fixture/FixtureUITests",
  "unit_test_target": "FixtureTests", "ui_test_target": "FixtureUITests"
}
```
- `project/`: the hand-made Xcode project (`App/Fixture/…`, §5.1) and `docs/outline.md` (§5.3),
  `docs/api/Counter.md` (written with `bull api`), `.swiftlint.yml` and `.swift-format` (§4).
- `app/Modules/Counter/`: `Contracts/CounterStore.swift` (the protocol, with the declarations-only
  marker) and `Counter.swift` (`actor Counter: CounterStore`, start value in its initializer,
  default 0).
- `tests/Counter/CounterTests.swift`: `@Suite struct CounterTests` checking both behaviors.
- `ui-tests/JourneyTests.swift`: `testJourney1_AppOpens()` launches with `-uiTesting` and waits for
  the app to be running in the foreground.

### 5.3 Fixture outline (`project/docs/outline.md`)
v1's outline in the v2 memo format: Purpose (a counter that only goes up; it checks the iOS gates
give the right verdicts); `## User journeys` — 1. **App opens** — a user opens the app; ends when
its first screen is in the foreground; `## Screens and navigation` — **Content**: the template's
first screen, serves journey 1; Constraints (stack `ios`, minimum iOS 18, offline, no accounts, no
sync, no third party); Out of scope: everything else; Data models: none; Build order `1. Counter
(depends on: none)`; module `Counter` (Files: `Contracts/CounterStore.swift | Counter.swift`;
Protocol `protocol CounterStore: Sendable { func value() async -> Int; func increment() async ->
Int }`; Behavior: a new counter's value is its start value (default 0); increment returns the count
plus one, which `value()` then returns; Contract: `docs/api/Counter.md`).

### 5.4 Cases
Every required id, plus `journey`, `journey-failing` and `adopt-mode` (no `interface-drift`: no
`[interfaces]`). Each change is the smallest Swift edit that triggers it:

| id | change | expect |
| --- | --- | --- |
| `clean` | none | pass, recorded |
| `fast` | none; `gates Counter --fast` | pass, not recorded |
| `no-tests` | `CounterTests.swift` → `import Testing` only | fail `tests`, "no tests ran" |
| `failing-test` | one `#expect` made wrong; `then` `gates --failed` | fail `tests`, the test's name; then fail, ran 1 |
| `build-warning` | an unused `let` in `Counter.swift` | fail `build`, `Counter.swift` |
| `lint` | a `try!` or `as!` in `Counter.swift` (still builds, still covered) | fail `lint` |
| `contract-change` | a new requirement in `CounterStore` (implemented in `Counter`) | fail `api` |
| `uncovered` | an untested method in `Counter` | fail `coverage`, `Counter.swift` |
| `exemption` | the same method with `// coverage-exempt: <reason>` | pass |
| `setup-broken` | the shared scheme file deleted | fail `setup`, "scheme" |
| `journey` | none; `gates --journeys` | pass, not recorded |
| `journey-failing` | the journey waits for an element that doesn't exist | fail `journeys`, `testJourney1_AppOpens` |
| `adopt-mode` | an active adoption in `status.json`; a legacy file outside `Modules/` with a warning | pass (legacy warnings don't count) |

## 6. Settings descriptions (stack.toml)

One line each, for `bull config show` and `bull stack setup`: `project` (the `.xcodeproj`, relative
to the part root), `scheme` (the shared scheme the gates build and test), `source_dir` (the app
target's folder; modules in `<source_dir>/Modules/<Module>/`), `test_dir` (the unit test target's
folder), `ui_test_dir` (the UI test target's folder; journeys in `JourneyTests.swift`),
`unit_test_target`, `ui_test_target` (target names), `simulator` (device name; empty → the newest
available iPhone).

## 7. Choices this note makes (for approval)

1. **No `DESIGN.md`.** The memo's `Files:` line has none and `bull stack test --static` doesn't
   require one; v1's iOS stack had none. The memo and this note carry the design. (Alternative: add
   one, a memo change and one more file in unit 5.)
2. **Lint = SwiftLint `--strict` + `swift-format lint --strict`** (§2.1, §4), with configs written
   into the app at setup so agents, Xcode and the gate use the same ones; SwiftLint becomes a
   required tool (Homebrew), swift-format comes with Xcode. The memo names both config files but not
   the commands. (Alternative: swift-format only, no Homebrew dependency.)
3. **No module-name setting.** `@testable import` uses the scheme name unless the target's
   `PRODUCT_MODULE_NAME` differs (v1 had `APP_MODULE`; the memo's settings don't). Nothing in the
   gates needs it. (Alternative: add a `module` setting.)
4. **Shared-scheme step in normal setup** (step 6). v1 had it only for adoptions and the fixture,
   but `readers.check` requires the scheme, and a user-only scheme isn't in git.
5. **Settings defaults follow Xcode's real layout**: `App/MyApp/MyApp.xcodeproj` (Xcode makes a
   `<App>/` folder inside `App/`), not the memo's shorter `App/<Name>.xcodeproj` example; plus a
   `ui_test_dir` default.
6. **Journeys reaching a service part** get `BULL_URL_<PART>` through the test runner (the gate
   passes it as `TEST_RUNNER_BULL_URL_<PART>`, which `xcodebuild` hands to the UI test process) and
   pass it to the app in `launchEnvironment`; missing → fail, not skip (as python_cli).
7. **Fixture in four folders** (§5.2): the hand-made Xcode project apart from the Swift sources and
   tests. `setup-broken` deletes the shared scheme; `adopt-mode` checks a legacy warning outside
   `Modules/` doesn't fail the build.
8. **The fixture's Xcode project** (§5.1) is needed before unit 6 runs its cases; until then they
   report "not run". I'll walk you through it once this note is approved, as the memo asks.

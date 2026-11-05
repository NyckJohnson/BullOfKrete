# iOS stack rules

Read with `ios-pipeline stack rules <agent>`: it prints the common section plus the agent's own.

## common
- Language: Swift 6 with strict concurrency, SwiftUI for new UI. File names end in `.swift`.
- Adopted apps keep their UIKit screens (UIKit, storyboards, xibs): the memo marks each screen
  `UI: UIKit` or `UI: SwiftUI`. A UIKit screen's logic lives in a tested view model; its view
  controller is a thin view in `Views/` (excluded from coverage, covered by the journey tests).
- Adoption terms the generic instructions use: the **clean-state launch option** is the `-uiTesting`
  launch argument; the **composition root** is `AppDependencies.swift` in the app shell; the **final
  switch** (Stage 6) moves every target to Swift 6 language mode; a screen's **UI technology** is
  `UI: UIKit` or `UI: SwiftUI`.
- During an adoption the project may still be in Swift 5 mode, but code in `Modules/` and module test
  folders must compile without warnings under Swift 6 rules (the gates check it).
- The whole app compiles as **one Swift module**: every type name must be unique across modules,
  and access control is `internal` by default. The compiler does not enforce module boundaries;
  a file may use another module's `Contracts/` types only, and only modules its memo entry lists.
- Naming follows the Swift API Design Guidelines.
- Tests: Swift Testing (`import Testing`, `@testable import <APP_MODULE>`, `@Test`, `#expect`,
  `#require`). Test files: `<APP_TEST_DIR>/<Module>/<File>Tests.swift`.
- UI tests: XCTest / XCUITest in the `<UI_TEST_TARGET>` folder.
- No force unwraps and no `try!` anywhere.
- Never edit the `.pbxproj` file: Xcode's synchronized folders add new files to their target.

## outline
- Protocols in the memo are Swift (fence them as ```swift), conforming to `Sendable`.
- Data models are `struct`, `Sendable`, `Codable`, `Equatable`, `Hashable` unless there's a reason.
- `Files:` lines use `.swift` names, e.g. `Counter.swift, CounterStore.swift | FileCounterStore.swift`.
- UI: views go in `Views/<Screen>View.swift`, view models next to the module's other files as
  `<Screen>ViewModel.swift`.

- Adoption memo (extra lines; `ios-pipeline template outline` shows them):
  - `## Legacy code` with `- App shell: <paths relative to APP_SOURCE_DIR>`: the entry point
    (`@main`), `AppDependencies.swift` (the composition root), assets, `Info.plist`, entitlements,
    launch screen. These never become a module.
    Also `- App shell tests: <paths relative to APP_TEST_DIR>`: test files and folders that belong to the
    app shell and no module (the shell's own tests, the test folder's `.swiftlint.yml`, a `.storekit`
    configuration the scheme points at). Files and folders listed there are not "old tests".
  - Per module: `- Legacy files:` (legacy paths it replaces; a file split across modules is listed in
    each, with `(part: <what>)`), `- Legacy tests:` (old test files it replaces), and
    `- Callers to repoint:` (legacy source files that use it; `none` if none).
  - Per screen in "Screens and navigation": `UI: UIKit` or `UI: SwiftUI`.
  - A UIKit screen's files: `Views/<Screen>ViewController.swift` (plus its storyboard or xib, if any)
    and `<Screen>ViewModel.swift`.

## skeleton-builder
- Models in `Contracts/`, exactly as the memo's Data models section; `struct`, `Sendable`,
  `Codable`, `Equatable`, `Hashable` unless the memo says otherwise.
- Stubs call `fatalError("Not implemented: <Type>.<method>")`.
- Mocks are `Mock<Protocol>` types in `Mocks/`, returning realistic sample data and recording calls.
- Placeholder test file per implementation file: a top-level `@Suite struct <File>Tests` with a
  single `@Test func placeholder() {}`.
- If the unit test target or Swift 6 language mode is missing (gates report it), don't fix the
  project; list the exact Xcode steps under `MANUAL STEPS FOR HUMAN`.
- The app's root view may show a placeholder.
- Feature mode: a stub for a new requirement is
  `fatalError("Not implemented: <Type>.<method> (feature <slug>)")`.
- Declaration-only files get a file-level coverage marker as their first line after the imports:
  `// coverage-exempt-file: declarations only`. Xcode records no coverage for a file without
  executable code, so without the marker the coverage gate fails it. This covers protocols with only
  requirements, enums with plain cases (no methods, computed properties or raw-value logic), structs
  with only stored properties and synthesized conformances, and `static let` constants. Anything with
  a method body, computed property, initializer body or default argument expression is not
  declaration-only: no marker.

- Adopt mode renames: a clashing legacy type `Foo` becomes `LegacyFoo` (same for its file name if
  the file is named after it). Rename with care for `@objc` names, storyboard and xib references
  (`customClass="Foo"`), `NSStringFromClass`, Codable keys and persisted type names: a rename must
  not change what is stored or what Interface Builder loads; keep the old runtime name with
  `@objc(Foo)` where one is needed.

## screen-builder
- The view goes in `<APP_SOURCE_DIR>/Modules/<Module>/Views/<Screen>View.swift`.
- The view model goes in `<APP_SOURCE_DIR>/Modules/<Module>/<Screen>ViewModel.swift`: `@MainActor`,
  `@Observable`, depending only on the protocols passed to its initializer.
- SwiftUI previews (`#Preview`) use the module's `Mock…` types.
- Accessibility: every interactive element has an accessibility label; support Dynamic Type (no fixed
  font sizes); works in dark mode.
- Add `accessibilityIdentifier`s to the elements the user journeys touch, named `<screen>.<element>`
  (e.g. `counterList.addButton`), so UI tests can find them.

- Adopt mode (`MODE: adopt-identifiers`): SwiftUI views get `.accessibilityIdentifier(...)`; UIKit
  views get `accessibilityIdentifier` set in code (`view.accessibilityIdentifier = "..."` in
  `viewDidLoad` or where the view is built) or in Interface Builder's Identity inspector for storyboard
  elements. Same `<screen>.<element>` names.

## test-writer
- Put each file's tests in a top-level suite named `<File>Tests` (`@Suite struct <File>Tests`).
  More suites per file are fine. Fast gate runs (`gates <Module> --fast`) run every **top-level**
  `struct`, `class` or `actor` in the module's test folder whose name ends in `Tests`, whatever the
  file is called; nested suites run with their parent. A top-level suite with any other name only
  runs in full gate runs, so always end suite names in `Tests`.
- Parameterized tests (`@Test(arguments:)`) for input tables.
- Name tests by behavior: `@Test("Deleting a missing counter throws notFound")`.
- Use a unique temporary directory per test (`FileManager.default.temporaryDirectory` plus a UUID).

## code-writer
- Swift 6 strict concurrency: no data races, no `@unchecked Sendable`, no `nonisolated(unsafe)`.
  UI-facing types are `@MainActor`.
- Errors: throw typed, documented errors. No `fatalError` except for genuinely unreachable states.
- Secrets in the Keychain only; never in `UserDefaults` or logs.
- No retain cycles in closures (`[weak self]` where needed); release observers, timers and file handles.
- Implementation details are `private` or `fileprivate` unless another file in the module needs them.
- Doc comments (`///`) on every non-private declaration in `Contracts/`, and on tricky logic.

- UIKit screens (adopted apps): the view controller is `@MainActor`, holds no business logic
  (it binds the view model's state to views and forwards actions), and lives in `Views/`.
  `@IBOutlet private weak var name: UIType!` is the one allowed implicitly unwrapped declaration.
  Observe the view model with Observation (`withObservationTracking` or `UIObservationTrackingEnabled`
  on iOS 18+) or Combine; cancel subscriptions on deinit.
- The view model is `@MainActor`, `@Observable` (or an `ObservableObject` if the minimum iOS is below
  17), testable without UIKit, and depends only on contracts.
- Adoption: `AppDependencies` (app shell) creates every live implementation once and passes it on;
  no new singletons or `static let shared`.

## reviewer
- Error handling: no force unwraps or `try!`; nothing swallowed with `try?` unless the spec allows it.
- Security: secrets only in the Keychain, never in logs or `UserDefaults`; HTTPS only (no ATS
  exceptions); file protection set on stored files; only the permissions and usage descriptions needed.
- Concurrency: UI work on the main actor; no data races, `@unchecked Sendable` or
  `nonisolated(unsafe)`; tasks cancel cleanly; no retain cycles; observers and timers are released.
- API design: Swift API Design Guidelines.
- Whole app: accessibility labels, Dynamic Type, dark mode, and no heavy work on the main thread at launch.
- Style nits SwiftLint would catch are not findings.
- A `// coverage-exempt-file:` marker is only valid on a declaration-only file (see the
  skeleton-builder rules). A method body, computed property, initializer body or default argument
  expression in a marked file is a blocker: remove the marker; the code needs tests.

- UIKit (adopted apps): view controllers are thin, as the code-writer rules say. Outlets other than
  `@IBOutlet private weak var x: T!`, logic in a view controller, or a singleton introduced during an
  adoption is a blocker.

## ui-test-writer
- One test method per journey in `<UI_TEST_TARGET>/JourneyTests.swift` (the UI test target's folder,
  next to the unit test folder), named after the journey: `testJourney1_AddFirstCounter()`.
- Find elements by `accessibilityIdentifier` (`<screen>.<element>`). If one is missing, return
  `blocked` listing which screen needs it; don't add them yourself.
- Launch with `app.launchArguments = ["-uiTesting"]`; the app uses that argument to start from a
  clean, in-memory state. If the app doesn't support it yet, return `blocked`.

- Adopt mode (`MODE: adopt-baseline`): put the journey tests in the UI test target's existing folder
  if it has one, in a new `JourneyTests.swift`. Leave any old UI tests alone.

## surveyor
- UI technology per screen: SwiftUI (`View` structs), UIKit in code (`UIViewController` subclasses
  building views), or Interface Builder (storyboard scenes, xibs: list the file and scene).
- Navigation: `NavigationStack`/`NavigationLink`, `UINavigationController` pushes, modal
  presentations, segues (storyboard identifiers), tab bars, coordinators.
- Singletons and globals: `static let shared`, global `let`/`var`, `UserDefaults.standard`,
  `NotificationCenter.default` use, `AppDelegate`/`SceneDelegate` state.
- Persistence: Core Data (`.xcdatamodeld`), SwiftData (`@Model`), files, `UserDefaults`, Keychain.
- Concurrency today: completion handlers, `DispatchQueue`, `async`/`await`, actors, `@MainActor`.
- You may open a file outside your list only to follow a type that a listed file uses, and only
  its declaration.

## coverage-analyst
- Exemption markers are Swift line comments: `// coverage-exempt: <reason>` at the end of the line,
  or `// coverage-exempt-begin: <reason>` … `// coverage-exempt-end` around a block.
- A file listed under "Files without coverage data" either has no executable code or never ran.
  Declaration-only (see the skeleton-builder rules for what counts): add
  `// coverage-exempt-file: declarations only` after its imports. Otherwise classify it `missed`.
- Typical infeasible code: system callbacks (app delegate, notification handlers), an unreachable
  `fatalError`, OS failures that can't be simulated.

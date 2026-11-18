# iOS stack: rules

`bull stack rules <agent>` prints `## common` plus that agent's section; `bull stack rules outline`
prints `## outline` only.

## common
- You write Swift 6 with strict concurrency. New UI is SwiftUI. File names end in `.swift` and are
  named after the main type they hold.
- The app's source folder is `<source_dir>`. Modules are folders at `<source_dir>/Modules/<Module>/`.
  Each holds `Contracts/` (what `bull api` reads), `Mocks/`, `Views/` and the implementation files.
  Module names are capitalized, as Swift type names are; so are `Modules/`, `Contracts/`, `Mocks/`
  and `Views/`.
- Unit tests live in `<test_dir>/<Module>/<File>Tests.swift`. Journey tests live in
  `<ui_test_dir>/JourneyTests.swift`.
- The whole app compiles as **one Swift module**. Every type name must be unique across modules,
  and access is `internal` by default. The compiler doesn't enforce module boundaries, so you do: a
  file may use another module's `Contracts/` types only, and only from modules its memo entry lists
  under `Depends on`. Review checks it.
- Name things by the Swift API Design Guidelines.
- Unit tests use Swift Testing: `import Testing`, `@testable import <AppModule>`, `@Test`,
  `#expect`, `#require`. `<AppModule>` is the app target's module name: the `scheme` setting,
  unless the app target's `PRODUCT_MODULE_NAME` build setting says otherwise.
- Journey tests use XCTest and XCUITest, in the UI test target.
- No force unwraps and no `try!`, anywhere. The one exception, UIKit outlets, is under
  `## code-writer`.
- Never edit the `.pbxproj` file. The project uses synchronized folders: Xcode adds new files to
  their target by itself.
- Lint is SwiftLint (`swiftlint lint --strict`) and swift-format (`xcrun swift-format lint
  --strict`), run on the module's source and test folders. They use the app's `.swiftlint.yml` and
  `.swift-format` at the part root (setup writes them), else the stack's own configs.
- Build output and result bundles live under the app's `.bull/` folder, never the global
  DerivedData. `bull stack run prune` deletes them when they grow.
- Words bull's general instructions use for adoptions mean this here:
  - the **clean-state launch option** is the `-uiTesting` launch argument;
  - the **composition root** is `AppDependencies.swift` in the app shell;
  - the **final switch** (adoption stage 6) moves every target to Swift 6 language mode;
  - a screen's **UI technology** is `UI: UIKit` or `UI: SwiftUI`.
- Adopted apps keep their UIKit screens (UIKit code, storyboards, xibs). The memo marks each screen
  `UI: UIKit` or `UI: SwiftUI`. A UIKit screen's logic lives in a tested view model. Its view
  controller is a thin view in `Views/`, left out of coverage and covered by the journey tests.
- While an adoption is active, the project may still be in Swift 5 mode. Code in `Modules/` and in
  module test folders must still compile without warnings under Swift 6 rules: the build gate fails
  on any warning there, and ignores warnings in legacy code.

## outline
- Protocols in the memo are Swift, fenced ```` ```swift ````, and conform to `Sendable`.
- Data models are `struct`s that are `Sendable`, `Codable`, `Equatable` and `Hashable`, unless the
  memo entry says why not.
- `Files:` lines use paths relative to the module folder, e.g. `Contracts/CounterStore.swift,
  Contracts/Counter.swift | FileCounterStore.swift`.
- UI: views go in `Views/<Screen>View.swift`; view models sit next to the module's other files as
  `<Screen>ViewModel.swift`. Each screen under "Screens and navigation" names its module.
- `## Constraints` names the minimum iOS version and any capability the app needs (iCloud, push
  notifications, background modes…). Setup turns them into Xcode steps.
- The app shell is not a module: the `@main` entry point, `AppDependencies.swift`, assets,
  `Info.plist`, entitlements and the launch screen.
- An adoption memo has extra lines; `bull template outline` shows them:
  - `## Legacy code` with `- App shell: <paths relative to source_dir>` (the app shell files
    above); `- App shell tests: <paths relative to test_dir>` (the shell's own tests, the test
    folder's `.swiftlint.yml`, a `.storekit` configuration the scheme points at: these are not old
    tests); then `- Legacy folders:` and `- Renames: Foo → LegacyFoo, …` as the template shows.
  - Per module: `- Legacy files:` (a file split across modules is listed in each, with `(part:
    <what>)`), `- Legacy tests:` and `- Callers to repoint:` (`none` if none).
  - Per screen: `UI: UIKit` or `UI: SwiftUI`. A UIKit screen's files are
    `Views/<Screen>ViewController.swift` (plus its storyboard or xib, if any) and
    `<Screen>ViewModel.swift`.

## skeleton-builder
- Put the models in `Contracts/`, exactly as the memo's Data models give them: `struct`,
  `Sendable`, `Codable`, `Equatable`, `Hashable` unless the memo says otherwise. Put the protocols
  in `Contracts/` exactly as drafted.
- Stubs call `fatalError("Not implemented: <Type>.<method>")`. In feature mode they call
  `fatalError("Not implemented: <Type>.<method> (feature <slug>)")`.
- Mocks are `Mock<Protocol>` types in `Mocks/`. They return realistic sample data and record calls.
- Write one placeholder test file per implementation file: a top-level `@Suite struct <File>Tests`
  with one `@Test func placeholder() {}`.
- The app's root view may show a placeholder.
- A declaration-only file gets `// coverage-exempt-file: declarations only` as its first line after
  the imports (within the first 10 lines). Xcode records no coverage for a file without executable
  code, so without the marker the coverage gate fails it. Declaration-only means: protocols with
  only requirements; enums with plain cases (no methods, computed properties or raw-value logic);
  structs with only stored properties and synthesized conformances; `static let` constants. A
  method body, computed property, initializer body or default argument expression makes a file not
  declaration-only: then it gets no marker.
- If the unit test target, the shared scheme or Swift 6 mode is missing (the setup gate or `bull
  stack check` says so), don't fix the project yourself. List the exact Xcode steps under
  `MANUAL STEPS FOR HUMAN`; `bull stack setup` has them.
- Adopt mode renames: a legacy type `Foo` that clashes becomes `LegacyFoo`, and so does its file if
  it is named after the type. Take care with `@objc` names, storyboard and xib references
  (`customClass="Foo"`), `NSStringFromClass`, `Codable` keys and persisted type names. A rename
  must not change what is stored or what Interface Builder loads: keep the old runtime name with
  `@objc(Foo)` where needed.
- Adopt mode scaffold: write an empty `AppDependencies.swift` composition root in the app shell,
  where the memo's `## Legacy code` puts it.

## screen-builder
- Put the view in `<source_dir>/Modules/<Module>/Views/<Screen>View.swift` and the view model in
  `<source_dir>/Modules/<Module>/<Screen>ViewModel.swift`. The view model is `@MainActor` and
  `@Observable`, and depends only on the protocols passed to its initializer.
- SwiftUI previews (`#Preview`) use the module's `Mock…` types.
- Accessibility: give every interactive element an accessibility label. Support Dynamic Type (no
  fixed font sizes). Make the screen work in dark mode.
- Test identifiers: put `.accessibilityIdentifier("<screen>.<element>")` on every element a journey
  touches, e.g. `counterList.addButton`.
- Adopt mode (`MODE: adopt-identifiers`): SwiftUI views get `.accessibilityIdentifier(...)`. UIKit
  views get `accessibilityIdentifier` set in code (in `viewDidLoad` or where the view is built), or
  in Interface Builder's Identity inspector for storyboard elements. Use the same names.

## test-writer
- Put each file's tests in a top-level suite named `<File>Tests` (`@Suite struct <File>Tests`).
  More suites per file are fine.
- `bull gates <Module> --fast` runs every **top-level** `struct`, `class` or `actor` in the
  module's test folder whose name ends in `Tests` (or that carries `@Suite`), whatever the file is
  called. Nested suites run with their parent. Always end suite names in `Tests`.
- Use parameterized tests (`@Test(arguments:)`) for input tables.
- Name tests by behavior: `@Test("Deleting a missing counter throws notFound")`.
- Give each test its own temporary directory (`FileManager.default.temporaryDirectory` plus a
  `UUID`), and remove it afterwards.
- Before you report, run from the part root: `xcrun swift-format format -i <your test files>`,
  then `swiftlint lint --fix <files>` and `swiftlint lint --strict <files>`. Fix what is left.

## code-writer
- Swift 6 strict concurrency: no data races, no `@unchecked Sendable`, no `nonisolated(unsafe)`.
  UI-facing types are `@MainActor`.
- Errors: throw typed, documented errors. No `fatalError` except for genuinely unreachable states.
- Secrets go in the Keychain only, never in `UserDefaults` or logs.
- No retain cycles in closures (use `[weak self]` where needed). Release observers, timers and
  file handles.
- Implementation details are `private` or `fileprivate` unless another file in the module needs
  them.
- Write doc comments (`///`) on every non-private declaration in `Contracts/`, and on tricky logic.
- Iterate with `bull gates --failed` (it reruns the tests that just failed), then confirm with
  `bull gates <Module> --fast`.
- UIKit screens (adopted apps): the view controller is `@MainActor`, holds no business logic (it
  binds the view model's state to views and forwards actions) and lives in `Views/`.
  `@IBOutlet private weak var name: UIType!` is the one implicitly unwrapped declaration you may
  write. Observe the view model with Observation (`withObservationTracking`, or
  `UIObservationTrackingEnabled` on iOS 18+) or Combine, and cancel subscriptions on deinit.
- The view model is `@MainActor` and `@Observable` (or `ObservableObject` if the minimum iOS is
  below 17). It is testable without UIKit and depends only on contracts.
- Adoption: `AppDependencies` (in the app shell) creates every live implementation once and passes
  it on through initializers. Add no new singletons and no `static let shared`.

## reviewer
- Error handling: no force unwraps or `try!`. Nothing swallowed with `try?` unless the spec allows
  it.
- Security: secrets only in the Keychain, never in logs or `UserDefaults`. HTTPS only, with no ATS
  exceptions. File protection set on stored files. Only the permissions and usage descriptions the
  app needs.
- Concurrency: UI work on the main actor. No data races, no `@unchecked Sendable`, no
  `nonisolated(unsafe)`. Tasks cancel cleanly. No retain cycles; observers and timers are released.
- API design: the Swift API Design Guidelines.
- Whole app (`SCOPE: whole app`): accessibility labels, Dynamic Type, dark mode, and no heavy work
  on the main thread at launch.
- Style nits SwiftLint or swift-format would catch are not findings.
- A `// coverage-exempt-file:` marker is valid only on a declaration-only file (see
  `## skeleton-builder` for what that means). A method body, computed property, initializer body or
  default argument expression in a marked file is a blocker: the marker goes, and the code needs
  tests.
- Cross-module use goes through the `Contracts/` of declared dependencies only (see `## common`).
- UIKit (adopted apps): view controllers stay thin, as the code-writer rules say. An outlet other
  than `@IBOutlet private weak var x: T!`, logic in a view controller, or a singleton introduced
  during an adoption is a blocker.

## coverage-analyst
- Markers are Swift line comments: `// coverage-exempt: <reason>` at the end of a line, or
  `// coverage-exempt-begin: <reason>` … `// coverage-exempt-end` around a block.
- A file under "Files without coverage data" has no executable code or never ran. If it is
  declaration-only (protocols with only requirements, plain enums, structs with only stored
  properties, `static let` constants), add `// coverage-exempt-file: declarations only` after its
  imports. Otherwise classify it `missed`.
- Typically infeasible to cover: system callbacks (app delegate, notification handlers), an
  unreachable `fatalError`, OS failures that can't be simulated.
- `Views/` and `Mocks/` are already left out of coverage. Don't mark them.

## journey-test-writer
- Write one test method per journey in `<ui_test_dir>/JourneyTests.swift`
  (`final class JourneyTests: XCTestCase`), named after the journey:
  `testJourney1_AddFirstCounter()`.
- Find elements by `accessibilityIdentifier` (`<screen>.<element>`). If one is missing, return
  `blocked` naming the screen that needs it. Don't add identifiers yourself.
- Launch with `app.launchArguments = ["-uiTesting"]`: the app uses that argument to start from a
  clean, in-memory state. If the app doesn't support it yet, return `blocked`.
- Wait for elements with `waitForExistence(timeout:)`. Never `sleep`.
- A journey that reaches a service part: bull passes the service's address to the test runner as
  `BULL_URL_<PART>`. Read it from `ProcessInfo.processInfo.environment` and hand it to the app in
  `app.launchEnvironment`. If it is missing, fail with a message naming the variable; don't skip.
- Adopt mode (`MODE: adopt-baseline`): put `JourneyTests.swift` in the UI test target's existing
  folder. Leave any old UI tests alone.

## surveyor
- UI technology per screen: SwiftUI (`View` structs), UIKit in code (`UIViewController` subclasses
  that build their views), or Interface Builder (storyboard scenes and xibs: list the file and the
  scene).
- Navigation: `NavigationStack`/`NavigationLink`, `UINavigationController` pushes, modal
  presentations, segues (with their storyboard identifiers), tab bars, coordinators.
- Singletons and globals: `static let shared`, global `let`/`var`, `UserDefaults.standard`,
  `NotificationCenter.default`, state in `AppDelegate`/`SceneDelegate`.
- Persistence: Core Data (`.xcdatamodeld`), SwiftData (`@Model`), files, `UserDefaults`, Keychain.
- Concurrency today: completion handlers, `DispatchQueue`, `async`/`await`, actors, `@MainActor`.
- You may open a file outside your list only to follow a type a listed file uses, and then only its
  declaration.

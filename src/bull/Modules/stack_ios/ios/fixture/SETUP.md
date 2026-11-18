# iOS fixture: the Xcode project (once, by hand)

`bull stack test ios` runs the iOS gates against this fixture. The Swift files, the memo and the
cases are in the repo; the Xcode project is made in Xcode once, on a Mac with Xcode 26 or later.
Until it exists every case reports "not run". It takes about ten minutes. Paths below are
relative to bull's repo.

1. Make the project's folder:
   ```sh
   mkdir -p src/bull/Modules/stack_ios/ios/fixture/project/App
   ```
2. **Create the project.** In Xcode choose File › New › Project › iOS › App, then:
   - Product Name: **Fixture** (the cases use this name)
   - Team: None
   - Organization Identifier: anything (e.g. `dev.bull`)
   - Interface: SwiftUI; Language: Swift
   - Testing System: **Swift Testing with XCUITests**
   - Storage: None

   Save it in `src/bull/Modules/stack_ios/ios/fixture/project/App/` and **uncheck "Create Git
   repository on my Mac"**.
3. **Swift 6.** For each of the targets Fixture, FixtureTests and FixtureUITests: Build Settings ›
   Swift Language Version (`SWIFT_VERSION`) → **Swift 6**.
4. **Actor isolation.** For Fixture and FixtureTests: Build Settings › Default Actor Isolation
   (`SWIFT_DEFAULT_ACTOR_ISOLATION`) → **nonisolated**.
5. **Minimum iOS 18.0** for every target (General › Minimum Deployments), so the fixture runs on
   more simulators.
6. **Shared scheme.** Product › Scheme › Manage Schemes…: tick **Shared** for Fixture. The cases
   need `App/Fixture/Fixture.xcodeproj/xcshareddata/xcschemes/Fixture.xcscheme`.
7. **Remove the template's tests, outside Xcode.** Quit Xcode first, then in
   `src/bull/Modules/stack_ios/ios/fixture/project/App/Fixture/`:
   - delete `FixtureTests/FixtureTests.swift`, `FixtureUITests/FixtureUITests.swift` and
     `FixtureUITests/FixtureUITestsLaunchTests.swift`;
   - `touch FixtureTests/.gitkeep FixtureUITests/.gitkeep`.

   Keep `Fixture/FixtureApp.swift`, `Fixture/ContentView.swift` and `Fixture/Assets.xcassets`.
   Why not in Xcode: deleting a folder's last file there removes the folder and its link to the
   target, so no test runs.
8. Run `bull stack test ios`: every case should pass (✅). If one doesn't, run
   `bull stack test ios --case <id>` and read its expected and got lines.
9. Commit `src/bull/Modules/stack_ios/ios/fixture/project/App` (no `xcuserdata/`, no
   `DerivedData/`).

## If the template's tests were deleted in Xcode

The test folders lost their link to their targets. To repair:

1. Recreate both folders, each with an empty `.gitkeep`:
   ```sh
   cd src/bull/Modules/stack_ios/ios/fixture/project/App/Fixture
   mkdir -p FixtureTests FixtureUITests
   touch FixtureTests/.gitkeep FixtureUITests/.gitkeep
   ```
2. Open the project in Xcode and drag each folder onto the project in the navigator. Choose
   **Create folders**, and tick only its own target: FixtureTests for `FixtureTests/`,
   FixtureUITests for `FixtureUITests/`.
3. Quit Xcode and check:
   ```sh
   grep -c PBXFileSystemSynchronizedRootGroup Fixture.xcodeproj/project.pbxproj
   ```
   A repaired project prints 5; a broken one prints 3.

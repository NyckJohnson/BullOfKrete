# iOS fixture: the Xcode project (once, by hand)

`ios-pipeline stack test ios` runs the iOS gates against this fixture. The Swift files, the memo and
the cases are in the repo; the Xcode project has to be made in Xcode, once, on a Mac with Xcode 26 or
later. Until it exists, every case reports "not run". About ten minutes.

1. In the pipeline repo: `mkdir -p stacks/ios/fixture/project/App`.
2. **Create the project.** Xcode › File › New › Project › iOS › App.
   - Product Name: **Fixture** (the cases use this name). Team: None. Organization Identifier:
     anything, e.g. `dev.pipeline`.
   - Interface: SwiftUI · Language: Swift · Testing System: **Swift Testing with XCUITests** ·
     Storage: None.
   - Save it in `stacks/ios/fixture/project/App/`, and **uncheck "Create Git repository on my Mac"**.
3. **Swift 6.** In Build Settings for the **Fixture**, **FixtureTests** and **FixtureUITests**
   targets: Swift Language Version = **Swift 6**.
4. **Actor isolation.** If Build Settings shows Default Actor Isolation, set it to **nonisolated** for
   Fixture and FixtureTests.
5. **Minimum iOS.** Deployment target **iOS 18.0** for every target, so the fixture runs on more
   simulators.
6. **Shared scheme.** Product › Scheme › Manage Schemes…, tick **Shared** for Fixture. (The stack test
   needs `Fixture.xcodeproj/xcshareddata/xcschemes/Fixture.xcscheme`.)
7. **Remove the template's tests, outside Xcode.** The fixture brings its own (`tests/`, `ui-tests/`),
   and the template's launch-performance test is slow. Quit Xcode first, then from the pipeline repo:
   ```sh
   cd stacks/ios/fixture/project/App/Fixture
   rm FixtureTests/FixtureTests.swift FixtureUITests/FixtureUITests.swift FixtureUITests/FixtureUITestsLaunchTests.swift
   touch FixtureTests/.gitkeep FixtureUITests/.gitkeep
   cd -
   ```
   Not in Xcode: deleting a folder's last file there removes the folder and its link to the test
   target, so the tests compile nothing and no test runs. The `.gitkeep` files keep the folders in git.
   Keep the app's own files (`FixtureApp.swift`, `ContentView.swift`, `Assets.xcassets`).
8. From the pipeline repo, run `ios-pipeline stack test ios`. Every case should be ✅.
   If one isn't, `ios-pipeline stack test ios --case <id> --keep --verbose` keeps that case's app
   and prints every command's output.
9. Commit `stacks/ios/fixture/project/App` (`git status` should show no `xcuserdata` or
   `DerivedData`; the pipeline's `.gitignore` excludes them).

## If the template's tests were deleted in Xcode

`ios-pipeline stack test ios` then fails with "no tests ran", and in a kept case app `stack check`
reports a test target that doesn't include its folder. To repair the project:

1. Quit Xcode. Recreate the folders: from the pipeline repo,
   `mkdir -p stacks/ios/fixture/project/App/Fixture/{FixtureTests,FixtureUITests}` and
   `touch stacks/ios/fixture/project/App/Fixture/{FixtureTests,FixtureUITests}/.gitkeep`.
2. Open the project. Drag `FixtureTests` from Finder onto the **Fixture** project at the top of the
   navigator; choose **Create folders**, and tick only the **FixtureTests** target. Do the same for
   `FixtureUITests`, ticking only **FixtureUITests**.
3. Quit Xcode, then check: `grep -c PBXFileSystemSynchronizedRootGroup
   stacks/ios/fixture/project/App/Fixture/Fixture.xcodeproj/project.pbxproj` should print 5: the
   section's begin and end markers, plus one folder each for Fixture, FixtureTests and FixtureUITests
   (a broken project prints 3).

import XCTest

final class JourneyTests: XCTestCase {
    /// Journey 1, App opens: the app launches into its first screen, in the foreground.
    @MainActor
    func testJourney1_AppOpens() {
        let app = XCUIApplication()
        app.launchArguments = ["-uiTesting"]
        app.launch()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 10))
    }
}

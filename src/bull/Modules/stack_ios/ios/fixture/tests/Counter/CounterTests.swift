import Testing

@testable import Fixture

@Suite struct CounterTests {
    @Test("A new counter's value is its start value, 0 by default")
    func startValue() async {
        #expect(await Counter().value() == 0)
        #expect(await Counter(start: 5).value() == 5)
    }

    @Test("Increment returns the count plus one, which value then returns")
    func increment() async {
        let counter = Counter(start: 3)
        #expect(await counter.increment() == 4)
        #expect(await counter.value() == 4)
    }
}

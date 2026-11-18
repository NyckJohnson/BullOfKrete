// coverage-exempt-file: declarations only

/// Holds a count that only goes up.
protocol CounterStore: Sendable {
    /// The current count: the start value until the first increment.
    func value() async -> Int

    /// Adds one to the count and returns the new count.
    func increment() async -> Int
}

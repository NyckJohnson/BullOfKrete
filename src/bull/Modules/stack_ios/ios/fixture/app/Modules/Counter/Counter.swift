/// A `CounterStore` that keeps its count in memory.
actor Counter: CounterStore {
    private var count: Int

    /// Creates a counter whose value is `start` until the first increment.
    init(start: Int = 0) {
        count = start
    }

    func value() -> Int {
        count
    }

    func increment() -> Int {
        count += 1
        return count
    }
}

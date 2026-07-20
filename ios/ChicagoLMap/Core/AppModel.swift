import SwiftUI
import Observation

@Observable @MainActor
final class AppModel {
    // MARK: Observed state

    var selectedLines: Set<CTALine> = Set(CTALine.allCases)
    var trains: [Train] = []
    var stations: [Station] = []
    var polylines: [RoutePolyline] = []
    var selectedStation: Station?
    var arrivals: StationArrivals?
    var arrivalsError: Bool = false
    var isLoadingArrivals: Bool = false
    var lastUpdated: Date?
    var isRefreshing: Bool = false
    var connectionLost: Bool = false

    /// Live trip tracking (following a boarded train by run number).
    let trip = TripTracker()

    var allSelected: Bool {
        selectedLines.count == CTALine.allCases.count
    }

    // MARK: Internal state (not observed)

    @ObservationIgnored private var isPolling = false
    @ObservationIgnored private var staticDataLoaded = false
    @ObservationIgnored private var refreshQueued = false
    @ObservationIgnored private var fetchingArrivalsMapid: Int?
    @ObservationIgnored private var arrivalsTask: Task<Void, Never>?

    // MARK: Lifecycle

    /// Loads the static map data (stations + route polylines) once, then runs
    /// the 15-second train polling loop until the surrounding task is cancelled.
    func start() async {
        if !staticDataLoaded {
            staticDataLoaded = true
            await loadStaticData()
        }

        guard !isPolling else { return }
        isPolling = true
        defer { isPolling = false }

        while !Task.isCancelled {
            await refreshTrains()
            do {
                try await Task.sleep(for: .seconds(15))
            } catch {
                break
            }
        }
    }

    // MARK: Trains

    /// Fetches live trains for every selected line concurrently. Guarded so
    /// overlapping calls (poll loop + chip taps) never run at the same time;
    /// a call that arrives while a refresh is in flight is coalesced into one
    /// follow-up pass rather than dropped, so chip taps always take effect.
    func refreshTrains() async {
        if isRefreshing {
            refreshQueued = true
            return
        }

        isRefreshing = true
        defer { isRefreshing = false }

        repeat {
            refreshQueued = false
            await fetchTrainsOnce()
        } while refreshQueued && !Task.isCancelled
    }

    private func fetchTrainsOnce() async {
        let lines = selectedLines
        guard !lines.isEmpty else {
            trains = []
            return
        }

        var fetched: [Train] = []
        var succeededLines: Set<CTALine> = []
        await withTaskGroup(of: (CTALine, [Train]?).self) { group in
            for line in lines {
                group.addTask {
                    (line, try? await APIClient.shared.trains(for: line))
                }
            }
            for await (line, batch) in group {
                if let batch {
                    succeededLines.insert(line)
                    fetched.append(contentsOf: batch)
                }
            }
        }

        guard !Task.isCancelled else { return }

        if succeededLines.isEmpty {
            connectionLost = true
        } else {
            // Selection may have changed while the fetches were in flight.
            // For lines whose fetch failed this cycle, keep the previous
            // poll's markers instead of blinking the whole line off the map.
            let stale = trains.filter {
                selectedLines.contains($0.line) && !succeededLines.contains($0.line)
            }
            trains = fetched.filter { selectedLines.contains($0.line) } + stale
            lastUpdated = Date()
            connectionLost = false
        }
    }

    // MARK: Line selection

    func toggle(_ line: CTALine) {
        if selectedLines.contains(line) {
            selectedLines.remove(line)
            trains.removeAll { $0.line == line }
        } else {
            selectedLines.insert(line)
            Task {
                await refreshTrains()
            }
        }
    }

    func selectAllLines() {
        selectedLines = Set(CTALine.allCases)
        Task {
            await refreshTrains()
        }
    }

    // MARK: Station selection & arrivals

    /// Selects a station and starts a 30-second arrivals auto-refresh loop,
    /// or clears the selection (and cancels the loop) when passed nil.
    func select(station: Station?) {
        arrivalsTask?.cancel()
        arrivalsTask = nil

        selectedStation = station

        // On deselect, leave `arrivals`/`arrivalsError`/`isLoadingArrivals`
        // untouched so the sheet doesn't flash the loading state during its
        // dismissal animation; the non-nil branch below resets all three
        // before loading the next station, so stale data can't leak.
        guard station != nil else { return }

        arrivals = nil
        arrivalsError = false
        isLoadingArrivals = false

        arrivalsTask = Task { [weak self] in
            while !Task.isCancelled {
                // The sheet can also be dismissed by setting `selectedStation`
                // to nil directly (sheet item binding) — stop looping then.
                guard let self, self.selectedStation != nil else { return }
                await self.refreshArrivals()
                do {
                    try await Task.sleep(for: .seconds(30))
                } catch {
                    return
                }
            }
        }
    }

    func refreshArrivals() async {
        guard let station = selectedStation else { return }
        // Keyed by station so a lingering fetch for a previously selected
        // station never suppresses the newly selected station's first fetch.
        guard fetchingArrivalsMapid != station.id else { return }
        fetchingArrivalsMapid = station.id
        defer {
            if fetchingArrivalsMapid == station.id {
                fetchingArrivalsMapid = nil
            }
        }

        if arrivals == nil {
            isLoadingArrivals = true
            arrivalsError = false
        }

        do {
            let result = try await APIClient.shared.arrivals(mapid: station.id, count: 12)
            // A stale fetch must not touch state owned by the new selection.
            guard selectedStation?.id == station.id else { return }
            arrivals = result
            arrivalsError = false
        } catch {
            guard selectedStation?.id == station.id else { return }
            // Keep showing stale arrivals if a background refresh fails;
            // only surface the error state when there is nothing to show.
            if arrivals == nil {
                arrivalsError = true
            }
        }
        isLoadingArrivals = false
    }

    // MARK: Static data

    /// Loads stations and polylines, retrying once after 3 seconds before
    /// surfacing `connectionLost`.
    private func loadStaticData() async {
        do {
            try await fetchStaticData()
        } catch {
            do {
                try await Task.sleep(for: .seconds(3))
                try await fetchStaticData()
            } catch {
                connectionLost = true
            }
        }
    }

    private func fetchStaticData() async throws {
        async let stationsResult = APIClient.shared.allStations()
        async let polylinesResult = APIClient.shared.routePolylines()
        let (fetchedStations, fetchedPolylines) = try await (stationsResult, polylinesResult)
        stations = fetchedStations
        polylines = fetchedPolylines
    }
}

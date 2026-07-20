//
//  TripTracker.swift
//  ChicagoLMap
//
//  Follows a single train by run number and maintains the trip timeline. It
//  polls /api/run/<run>/follow every 20 s; because that endpoint is driven by
//  CTA's ttfollow predictions (schedule + signal data), tracking keeps working
//  underground where GPS does not.
//
//  As the ride progresses, stops that drop off the "upcoming" list are recorded
//  as passed at roughly the time they disappeared, so the timeline shows real
//  (grey) times behind the train and predicted times ahead of it.
//

import Foundation
import Observation

@Observable @MainActor
final class TripTracker {
    // MARK: Observed state

    private(set) var runNumber: String?
    private(set) var line: CTALine?
    private(set) var boardingStationName: String?
    private(set) var destination: String?
    private(set) var stops: [TripStop] = []
    private(set) var lastUpdated: Date?
    private(set) var loadFailed: Bool = false
    private(set) var isLoading: Bool = false

    var isTracking: Bool { runNumber != nil }

    // MARK: Internal bookkeeping (not observed)

    @ObservationIgnored private var pollTask: Task<Void, Never>?
    @ObservationIgnored private var order: [Int] = []            // station ids in first-seen (travel) order
    @ObservationIgnored private var known: [Int: TripStop] = [:] // latest snapshot per station
    @ObservationIgnored private var passObserved: [Int: Date] = [:]
    @ObservationIgnored private var prevUpcoming: Set<Int> = []

    // MARK: Control

    /// Begins tracking a run, replacing any trip already in progress.
    func board(run: String, line: CTALine?, boardingStation: String?, destination: String?) {
        end()
        runNumber = run
        self.line = line
        boardingStationName = boardingStation
        self.destination = destination
        isLoading = true

        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                guard let self, self.runNumber != nil else { return }
                await self.refresh()
                do {
                    try await Task.sleep(for: .seconds(20))
                } catch {
                    return
                }
            }
        }
    }

    /// Stops tracking and clears all trip state.
    func end() {
        pollTask?.cancel()
        pollTask = nil
        runNumber = nil
        line = nil
        boardingStationName = nil
        destination = nil
        stops = []
        lastUpdated = nil
        loadFailed = false
        isLoading = false
        order = []
        known = [:]
        passObserved = [:]
        prevUpcoming = []
    }

    /// Fetches the latest follow data and rebuilds the timeline.
    func refresh() async {
        guard let run = runNumber else { return }
        do {
            let follow = try await APIClient.shared.runFollow(runNumber: run)
            guard runNumber == run else { return }   // trip changed while in flight
            apply(follow)
            loadFailed = false
            lastUpdated = Date()
        } catch {
            guard runNumber == run else { return }
            // Keep the last good timeline; only surface an error with nothing shown.
            if stops.isEmpty { loadFailed = true }
        }
        isLoading = false
    }

    // MARK: Timeline assembly

    private func apply(_ follow: RunFollow) {
        if let dest = follow.destination { destination = dest }

        let now = Date()
        let upcoming: [TripStop] = follow.stops.compactMap { dto in
            guard let sid = dto.stationId else { return nil }
            return TripStop(
                stationId: sid,
                name: dto.stationName ?? "Station",
                etaMinutes: dto.etaMinutes,
                scheduledDate: dto.scheduledDate,
                predictedDate: dto.predictedDate,
                delayMinutes: dto.delayMinutes,
                delayStatus: dto.delayStatus,
                predictorActive: dto.predictorActive,
                isApproaching: dto.isApproaching,
                status: .upcoming,
                observedPassTime: nil
            )
        }
        let upcomingIds = Set(upcoming.map(\.stationId))

        // Any stop that was upcoming last poll but isn't now was just passed.
        for id in prevUpcoming where !upcomingIds.contains(id) {
            if passObserved[id] == nil { passObserved[id] = now }
        }
        prevUpcoming = upcomingIds

        // Register new stops in travel order; refresh known snapshots.
        for stop in upcoming {
            if known[stop.stationId] == nil { order.append(stop.stationId) }
            known[stop.stationId] = stop
        }

        // Build the display timeline: passed stops (in travel order) then the
        // current stop and everything ahead of it.
        var timeline: [TripStop] = []
        for id in order where !upcomingIds.contains(id) {
            guard var stop = known[id] else { continue }
            stop.status = .passed
            stop.observedPassTime = passObserved[id]
            timeline.append(stop)
        }
        for (index, var stop) in upcoming.enumerated() {
            stop.status = (index == 0) ? .current : .upcoming
            timeline.append(stop)
        }
        stops = timeline
    }
}

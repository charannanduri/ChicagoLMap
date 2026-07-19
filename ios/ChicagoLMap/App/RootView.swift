//
//  RootView.swift
//  ChicagoLMap
//
//  Root composition: the full-bleed live map, a Liquid Glass title bar and
//  settings/trip controls at the top, the line-filter chip row + status pill at
//  the bottom, and the station arrivals, settings, and trip sheets.
//

import SwiftUI

struct RootView: View {
    @State private var model = AppModel()
    @State private var location = LocationProvider()
    @State private var showSettings = false
    @State private var tripFlow: TripFlow?
    @State private var pendingBoard: PendingBoard?

    private enum TripFlow: Int, Identifiable {
        case board, active
        var id: Int { rawValue }
    }

    private struct PendingBoard {
        let run: String
        let line: CTALine?
        let station: String?
        let destination: String?
    }

    var body: some View {
        ZStack {
            TrainMapView(model: model)

            VStack(spacing: 0) {
                topBar
                Spacer()
                bottomControls
            }
        }
        .background(Theme.background)
        .sheet(item: $model.selectedStation, onDismiss: {
            // Interactive drag-to-dismiss writes nil straight through the
            // binding, bypassing the model; route it through select(station:)
            // so the arrivals refresh task is always cancelled on deselect.
            model.select(station: nil)
            presentPendingTripIfNeeded()
        }) { _ in
            StationSheet(model: model, onBoard: { arrival, line in
                startTrip(arrival: arrival, line: line, station: model.selectedStation?.name)
            })
            .presentationDetents([.fraction(0.45), .large])
            .presentationDragIndicator(.visible)
            .presentationBackground(.thinMaterial)
        }
        .task {
            await model.start()
        }
    }

    // MARK: - Top bar

    private var topBar: some View {
        HStack(spacing: 8) {
            titleBar
            Spacer(minLength: 8)
            tripButton
            settingsButton
        }
        .padding(.horizontal, 14)
        .padding(.top, 8)
    }

    private var titleBar: some View {
        HStack(spacing: 8) {
            Text("Chicago 'L' Live")
                .font(.headline)
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.8)

            if !model.trains.isEmpty {
                Text("·")
                    .font(.headline)
                    .foregroundStyle(Theme.secondaryText)
                Text("\(model.trains.count)")
                    .font(.subheadline.weight(.semibold).monospacedDigit())
                    .foregroundStyle(Theme.secondaryText)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .liquidGlassCapsule()
        .animation(.default, value: model.trains.count)
        .accessibilityElement(children: .combine)
    }

    private var tripButton: some View {
        Button {
            tripFlow = model.trip.isTracking ? .active : .board
        } label: {
            HStack(spacing: 6) {
                Image(systemName: model.trip.isTracking ? "figure.seated.side" : "tram.fill")
                    .font(.subheadline.weight(.semibold))
                if model.trip.isTracking {
                    Text("On a train")
                        .font(.subheadline.weight(.semibold))
                }
            }
            .foregroundStyle(model.trip.isTracking ? .white : .white)
            .padding(.horizontal, model.trip.isTracking ? 14 : 0)
            .frame(minWidth: 44, minHeight: 44)
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .background {
            if model.trip.isTracking {
                Capsule().fill((model.trip.line?.color ?? .accentColor).opacity(0.85))
            }
        }
        .liquidGlassCapsule(interactive: !model.trip.isTracking)
        .animation(.spring(response: 0.3, dampingFraction: 0.7), value: model.trip.isTracking)
        .accessibilityLabel(model.trip.isTracking ? "View your trip" : "Board a train")
        // Trip sheet is hosted here so it never shares a view with another sheet.
        .sheet(item: $tripFlow) { flow in
            tripSheet(for: flow)
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
                .presentationBackground(.thinMaterial)
        }
    }

    private var settingsButton: some View {
        Button {
            showSettings = true
        } label: {
            Image(systemName: "gearshape.fill")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.white)
                .frame(width: 44, height: 44)
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .liquidGlass(in: Circle(), interactive: true)
        .accessibilityLabel("Settings")
        .sheet(isPresented: $showSettings) {
            SettingsView(onClose: { showSettings = false })
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
                .presentationBackground(.thinMaterial)
        }
    }

    @ViewBuilder
    private func tripSheet(for flow: TripFlow) -> some View {
        switch flow {
        case .board:
            BoardTrainView(
                model: model,
                location: location,
                onBoard: { arrival, line, station in
                    model.trip.board(
                        run: arrival.runNumber ?? "",
                        line: line,
                        boardingStation: station,
                        destination: arrival.destination
                    )
                    tripFlow = .active
                },
                onClose: { tripFlow = nil }
            )
        case .active:
            TripView(model: model, onEnd: {
                model.trip.end()
                tripFlow = nil
            })
        }
    }

    // MARK: - Bottom controls

    private var bottomControls: some View {
        VStack(spacing: 10) {
            StatusPill(
                lastUpdated: model.lastUpdated,
                connectionLost: model.connectionLost
            )

            GlassGroup(spacing: 12) {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        AllLinesChip(isSelected: model.allSelected) {
                            model.selectAllLines()
                        }

                        ForEach(CTALine.allCases) { line in
                            LineChip(
                                line: line,
                                isSelected: model.selectedLines.contains(line)
                            ) {
                                model.toggle(line)
                            }
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 4)
                }
            }
        }
        .padding(.bottom, 8)
    }

    // MARK: - Boarding flow

    /// Boarding from the station sheet: remember the run, dismiss the station
    /// sheet, then present the trip once dismissal finishes (avoids stacking two
    /// sheets at once).
    private func startTrip(arrival: Arrival, line: CTALine?, station: String?) {
        pendingBoard = PendingBoard(
            run: arrival.runNumber ?? "",
            line: line,
            station: station,
            destination: arrival.destination
        )
        model.select(station: nil)
    }

    private func presentPendingTripIfNeeded() {
        guard let pending = pendingBoard else { return }
        pendingBoard = nil
        model.trip.board(
            run: pending.run,
            line: pending.line,
            boardingStation: pending.station,
            destination: pending.destination
        )
        tripFlow = .active
    }
}

#Preview {
    RootView()
        .preferredColorScheme(.dark)
}

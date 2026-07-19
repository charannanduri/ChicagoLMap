//
//  StationSheet.swift
//  ChicagoLMap
//
//  Sheet content for a selected station: header with the station name, its
//  line chips, refresh and close controls, then the arrivals grouped by
//  direction. Handles loading, error, and empty states. Presented from
//  RootView via .sheet(item:) with a .thinMaterial presentation background.
//

import SwiftUI

struct StationSheet: View {
    @Bindable var model: AppModel
    /// Invoked when the rider taps "Board" on an arrival.
    var onBoard: ((Arrival, CTALine?) -> Void)? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
                .padding(.horizontal, 20)
                .padding(.top, 22)
                .padding(.bottom, 14)

            content
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    }

    // MARK: - Header

    private var header: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 8) {
                Text(stationName)
                    .font(.title2.bold())
                    .foregroundStyle(.white)
                    .lineLimit(2)
                    .minimumScaleFactor(0.7)

                if !stationLines.isEmpty {
                    HStack(spacing: 6) {
                        ForEach(stationLines) { line in
                            StationLineChip(line: line)
                        }
                    }
                }
            }

            Spacer(minLength: 0)

            HStack(spacing: 10) {
                refreshButton
                closeButton
            }
        }
    }

    private var refreshButton: some View {
        Button {
            Task { await model.refreshArrivals() }
        } label: {
            Image(systemName: "arrow.clockwise")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.white)
                .frame(width: 34, height: 34)
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .liquidGlass(in: Circle(), interactive: true)
        .disabled(model.isLoadingArrivals)
        .opacity(model.isLoadingArrivals ? 0.5 : 1.0)
        .accessibilityLabel("Refresh arrivals")
    }

    private var closeButton: some View {
        Button {
            model.select(station: nil)
        } label: {
            Image(systemName: "xmark")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.white)
                .frame(width: 34, height: 34)
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .liquidGlass(in: Circle(), interactive: true)
        .accessibilityLabel("Close")
    }

    // MARK: - Content

    @ViewBuilder
    private var content: some View {
        if let arrivals = model.arrivals {
            if hasAnyTrains(in: arrivals) {
                directionsList(arrivals)
            } else {
                emptyState
            }
        } else if model.arrivalsError {
            errorState
        } else {
            loadingState
        }
    }

    private func directionsList(_ arrivals: StationArrivals) -> some View {
        ScrollView {
            GlassGroup(spacing: 12) {
                LazyVStack(alignment: .leading, spacing: 12) {
                    ForEach(arrivals.directions) { group in
                        DirectionSection(group: group, onBoard: onBoard)
                    }
                }
            }
            .padding(.horizontal, 20)
            .padding(.top, 4)
            .padding(.bottom, 28)
        }
        .scrollIndicators(.hidden)
        .animation(.default, value: arrivals.directions.map(\.id))
    }

    private var loadingState: some View {
        VStack(spacing: 14) {
            ProgressView()
                .controlSize(.large)
                .tint(.white)
            Text("Loading arrivals…")
                .font(.footnote)
                .foregroundStyle(Theme.secondaryText)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.bottom, 30)
    }

    private var errorState: some View {
        VStack(spacing: 14) {
            Image(systemName: "wifi.exclamationmark")
                .font(.system(size: 34, weight: .medium))
                .foregroundStyle(Theme.secondaryText)

            Text("Couldn't load arrivals")
                .font(.headline)
                .foregroundStyle(.white)

            Button {
                Task { await model.refreshArrivals() }
            } label: {
                Text("Retry")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 22)
                    .frame(minHeight: 40)
                    .contentShape(Capsule())
            }
            .buttonStyle(.plain)
            .liquidGlassCapsule(interactive: true)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.bottom, 30)
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "tram")
                .font(.system(size: 34, weight: .medium))
                .foregroundStyle(Theme.secondaryText)

            Text("No upcoming arrivals")
                .font(.headline)
                .foregroundStyle(.white)

            Text("Check back in a few minutes.")
                .font(.footnote)
                .foregroundStyle(Theme.secondaryText)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.bottom, 30)
    }

    // MARK: - Helpers

    private var stationName: String {
        model.selectedStation?.name
            ?? model.arrivals?.stationName
            ?? "Station"
    }

    /// The station's lines in canonical CTA order.
    private var stationLines: [CTALine] {
        guard let lines = model.selectedStation?.lines else { return [] }
        return CTALine.allCases.filter { lines.contains($0) }
    }

    private func hasAnyTrains(in arrivals: StationArrivals) -> Bool {
        arrivals.directions.contains { !$0.trains.isEmpty }
    }
}

// MARK: - StationLineChip

/// Small colored capsule naming one line served by the station.
private struct StationLineChip: View {
    let line: CTALine

    var body: some View {
        Text(line.displayName)
            .font(.caption2.weight(.bold))
            .foregroundStyle(line == .yellow ? Color.black.opacity(0.85) : .white)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(Capsule().fill(line.color))
            .overlay(Capsule().stroke(Color.white.opacity(0.2), lineWidth: 0.5))
            .accessibilityLabel("\(line.displayName) Line")
    }
}

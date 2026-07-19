//
//  RootView.swift
//  ChicagoLMap
//
//  Root composition: the full-bleed live map, a Liquid Glass title bar at the
//  top, the line-filter chip row + status pill at the bottom, and the station
//  arrivals sheet.
//

import SwiftUI

struct RootView: View {
    @State private var model = AppModel()

    var body: some View {
        ZStack {
            TrainMapView(model: model)

            VStack(spacing: 0) {
                titleBar
                Spacer()
                bottomControls
            }
        }
        .background(Theme.background)
        .sheet(item: $model.selectedStation, onDismiss: {
            // Interactive drag-to-dismiss writes nil straight through the
            // binding, bypassing the model; route it through select(station:)
            // so the arrivals refresh task is always cancelled on deselect.
            // select(station: nil) is idempotent, so the X-button path
            // reaching here a second time is harmless.
            model.select(station: nil)
        }) { _ in
            StationSheet(model: model)
                .presentationDetents([.fraction(0.45), .large])
                .presentationDragIndicator(.visible)
                .presentationBackground(.thinMaterial)
        }
        .task {
            await model.start()
        }
    }

    // MARK: - Title bar

    private var titleBar: some View {
        HStack(spacing: 8) {
            Text("Chicago 'L' Live")
                .font(.headline)
                .foregroundStyle(.white)

            if !model.trains.isEmpty {
                Text("·")
                    .font(.headline)
                    .foregroundStyle(Theme.secondaryText)
                Text("\(model.trains.count) trains")
                    .font(.subheadline.weight(.semibold).monospacedDigit())
                    .foregroundStyle(Theme.secondaryText)
            }
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 10)
        .liquidGlassCapsule()
        .padding(.top, 8)
        .animation(.default, value: model.trains.count)
        .accessibilityElement(children: .combine)
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
}

#Preview {
    RootView()
        .preferredColorScheme(.dark)
}

//
//  SettingsView.swift
//  ChicagoLMap
//
//  App preferences sheet. Currently exposes the time-format choice used across
//  the station arrivals and live trip views.
//

import SwiftUI

struct SettingsView: View {
    @AppStorage(timeFormatDefaultsKey) private var timeFormat: TimeFormat = .relative
    let onClose: () -> Void

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    timeFormatSection
                    AlertsSection()
                    LegendSection()
                    HowPredictionsSection()
                    aboutSection
                }
                .padding(20)
            }
            .scrollIndicators(.hidden)
            .background(Theme.background)
            .navigationTitle("Info & Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done", action: onClose)
                        .foregroundStyle(.white)
                }
            }
            .toolbarBackground(.hidden, for: .navigationBar)
        }
        .preferredColorScheme(.dark)
    }

    // MARK: - Time format

    private var timeFormatSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionTitle("Arrival times")

            Picker("Show times as", selection: $timeFormat) {
                ForEach(TimeFormat.allCases) { format in
                    Text(format.label).tag(format)
                }
            }
            .pickerStyle(.segmented)

            Text(timeFormat.example)
                .font(.footnote)
                .foregroundStyle(Theme.secondaryText)

            Text(timeFormat == .relative
                 ? "Times count down in minutes until each train arrives."
                 : "Times show the clock time each train is expected — the CTA schedule next to our prediction.")
                .font(.caption)
                .foregroundStyle(Theme.secondaryText.opacity(0.85))
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .liquidGlass(in: RoundedRectangle(cornerRadius: 20, style: .continuous))
    }

    // MARK: - About

    private var aboutSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            sectionTitle("About")
            Text("Chicago 'L' Live shows every train on the map in real time, with machine-learned delay predictions from live data collected around the clock.")
                .font(.caption)
                .foregroundStyle(Theme.secondaryText)
                .fixedSize(horizontal: false, vertical: true)

            // Attribution for the upstream data, and a plain statement that we
            // are not affiliated with the CTA.
            Text("Live arrival data from the Chicago Transit Authority. Not affiliated with or endorsed by the CTA.")
                .font(.caption2)
                .foregroundStyle(Theme.secondaryText.opacity(0.8))
                .fixedSize(horizontal: false, vertical: true)

            Divider().overlay(Color.white.opacity(0.08))

            colophon
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .liquidGlass(in: RoundedRectangle(cornerRadius: 20, style: .continuous))
    }

    private var colophon: some View {
        VStack(alignment: .leading, spacing: 4) {
            // Markdown in a SwiftUI Text renders the link and makes it tappable.
            Text("Built in Chicago by [Charan Nanduri](https://linkedin.com/in/charannanduri), with a little help from my friend Claude.")
                .font(.caption2)
                .foregroundStyle(Theme.secondaryText)
                .tint(.white.opacity(0.85))
                .fixedSize(horizontal: false, vertical: true)
            Text("2026")
                .font(.caption2)
                .foregroundStyle(Theme.secondaryText.opacity(0.7))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func sectionTitle(_ text: String) -> some View {
        Text(text.uppercased())
            .font(.caption2.weight(.bold))
            .foregroundStyle(Theme.secondaryText)
            .tracking(0.8)
    }
}

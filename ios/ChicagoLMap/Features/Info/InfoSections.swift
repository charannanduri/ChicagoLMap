//
//  InfoSections.swift
//  ChicagoLMap
//
//  Reusable info cards shown in the Info & Settings sheet: a symbol legend, an
//  explanation of how predictions are derived, and live CTA service alerts.
//

import SwiftUI

// MARK: - Card scaffold

private struct InfoCard<Content: View>: View {
    let title: String
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title.uppercased())
                .font(.caption2.weight(.bold))
                .foregroundStyle(Theme.secondaryText)
                .tracking(0.8)
            content
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .liquidGlass(in: RoundedRectangle(cornerRadius: 20, style: .continuous))
    }
}

/// Small colored capsule naming one line.
struct MiniLineChip: View {
    let line: CTALine

    var body: some View {
        Text(line.displayName)
            .font(.caption2.weight(.bold))
            .foregroundStyle(line == .yellow ? Color.black.opacity(0.85) : .white)
            .padding(.horizontal, 7)
            .padding(.vertical, 2)
            .background(Capsule().fill(line.color))
    }
}

// MARK: - Legend

struct LegendSection: View {
    var body: some View {
        InfoCard(title: "What the symbols mean") {
            VStack(alignment: .leading, spacing: 14) {
                row(
                    symbol: AnyView(
                        Image(systemName: "exclamationmark.triangle.fill")
                            .font(.subheadline)
                            .foregroundStyle(.yellow)
                    ),
                    text: "The CTA has flagged this train as delayed."
                )
                row(
                    symbol: AnyView(
                        ArrivalPill(kind: .scheduled, label: "Scheduled", value: "4 min", tint: nil)
                    ),
                    text: "The CTA Train Tracker's own arrival estimate."
                )
                row(
                    symbol: AnyView(
                        ArrivalPill(kind: .predicted, label: "Predicted", value: "~5 min", tint: CTALine.blue.color)
                    ),
                    text: "Our machine-learning estimate of the real arrival time."
                )
                row(
                    symbol: AnyView(
                        Text("Now")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(.white)
                    ),
                    text: "The train is arriving or approaching the platform."
                )
                row(
                    symbol: AnyView(
                        Circle().fill(Color.green).frame(width: 9, height: 9)
                    ),
                    text: "Live data is updating. A red dot means the connection dropped."
                )
                row(
                    symbol: AnyView(
                        HStack(spacing: 3) {
                            MiniLineChip(line: .red)
                            MiniLineChip(line: .blue)
                        }
                    ),
                    text: "Which 'L' line the train runs on."
                )
            }
        }
    }

    private func row(symbol: AnyView, text: String) -> some View {
        HStack(alignment: .center, spacing: 12) {
            symbol.frame(width: 92, alignment: .leading)
            Text(text)
                .font(.footnote)
                .foregroundStyle(Theme.secondaryText)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
    }
}

// MARK: - How predictions work

struct HowPredictionsSection: View {
    var body: some View {
        InfoCard(title: "How our predictions work") {
            VStack(alignment: .leading, spacing: 10) {
                Text("The CTA's own arrival estimate — the “Scheduled” time — comes straight from the CTA Train Tracker. Our “Predicted” time layers a machine-learning model on top of it.")
                Text("The model (gradient-boosted trees) is trained on months of arrivals we collect every few minutes. For each train approaching a station it learns how the CTA's estimate typically drifts — using the line, station, direction, time of day, day of week, whether it's rush hour, how quickly the ETA has been changing, and the gap to the trains ahead and behind.")
                Text("From those it predicts how many minutes early or late the train will really be versus the CTA estimate, and shows you the corrected time. It retrains every week on fresh data. Predictions are strongest on the Red and Blue lines, where we have the most data, and improve elsewhere as we collect more.")
                Text("Your accuracy feedback — the +/− control on each train — feeds back into this.")
                    .foregroundStyle(Theme.secondaryText)
            }
            .font(.footnote)
            .foregroundStyle(.white.opacity(0.9))
            .fixedSize(horizontal: false, vertical: true)
        }
    }
}

// MARK: - Service alerts

struct AlertsSection: View {
    @State private var alerts: [ServiceAlert] = []
    @State private var isLoading = true
    @State private var failed = false

    var body: some View {
        InfoCard(title: "Service alerts") {
            if isLoading {
                HStack(spacing: 10) {
                    ProgressView().tint(.white)
                    Text("Checking for alerts…")
                        .font(.footnote)
                        .foregroundStyle(Theme.secondaryText)
                }
            } else if failed {
                Text("Couldn't load alerts.")
                    .font(.footnote)
                    .foregroundStyle(Theme.secondaryText)
            } else if alerts.isEmpty {
                HStack(spacing: 8) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                    Text("No active service alerts.")
                        .font(.footnote)
                        .foregroundStyle(Theme.secondaryText)
                }
            } else {
                VStack(alignment: .leading, spacing: 14) {
                    ForEach(alerts.prefix(12)) { alert in
                        AlertRow(alert: alert)
                        if alert.id != alerts.prefix(12).last?.id {
                            Divider().overlay(Color.white.opacity(0.08))
                        }
                    }
                }
            }
        }
        .task {
            await load()
        }
    }

    private func load() async {
        isLoading = true
        failed = false
        do {
            alerts = try await APIClient.shared.alerts()
        } catch {
            failed = true
        }
        isLoading = false
    }
}

private struct AlertRow: View {
    let alert: ServiceAlert

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if !alert.headline.isEmpty {
                Text(alert.headline)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(.white)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(spacing: 6) {
                if !alert.impact.isEmpty {
                    Text(alert.impact)
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(.orange)
                        .padding(.horizontal, 7)
                        .padding(.vertical, 2)
                        .background(Capsule().fill(Color.orange.opacity(0.15)))
                        .overlay(Capsule().stroke(Color.orange.opacity(0.4), lineWidth: 0.5))
                }
                ForEach(alert.lines) { line in
                    MiniLineChip(line: line)
                }
            }
            if !alert.description.isEmpty {
                Text(alert.description)
                    .font(.caption)
                    .foregroundStyle(Theme.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

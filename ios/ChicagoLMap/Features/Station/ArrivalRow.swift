//
//  ArrivalRow.swift
//  ChicagoLMap
//
//  One direction group ("Red · toward 95th/Dan Ryan") and its arrival rows —
//  the marquee ML surface. Each row shows the CTA "Scheduled" ETA pill next to
//  the line-tinted ML "Predicted" pill, with the delay-status caption beneath.
//

import SwiftUI

// MARK: - DirectionSection

/// A glass card for one service direction: line-colored route chip +
/// direction label header, followed by up to three `ArrivalRow`s.
struct DirectionSection: View {
    let group: DirectionGroup

    private var visibleArrivals: [Arrival] {
        Array(group.trains.prefix(3))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header

            if visibleArrivals.isEmpty {
                Text("No trains tracked")
                    .font(.footnote)
                    .foregroundStyle(Theme.secondaryText)
                    .padding(.vertical, 2)
            } else {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(visibleArrivals.enumerated()), id: \.offset) { index, arrival in
                        ArrivalRow(arrival: arrival, line: group.line)
                        if index < visibleArrivals.count - 1 {
                            Divider()
                                .overlay(Color.white.opacity(0.08))
                        }
                    }
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .liquidGlass(in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .accessibilityElement(children: .contain)
    }

    private var header: some View {
        HStack(spacing: 8) {
            routeChip
            Text(group.directionLabel)
                .font(.footnote.weight(.semibold))
                .foregroundStyle(Theme.secondaryText)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
            Spacer(minLength: 0)
        }
    }

    private var routeChip: some View {
        Text(group.line?.displayName ?? group.route)
            .font(.caption.weight(.bold))
            .foregroundStyle(chipTextColor)
            .padding(.horizontal, 9)
            .padding(.vertical, 3)
            .background(Capsule().fill(group.line?.color ?? Color.gray))
            .overlay(Capsule().stroke(Color.white.opacity(0.2), lineWidth: 0.5))
    }

    private var chipTextColor: Color {
        // The Yellow Line's bright fill needs dark text; every other line
        // reads best with white.
        group.line == .yellow ? Color.black.opacity(0.85) : .white
    }
}

// MARK: - ArrivalRow

/// A single arrival: destination, the CTA "Scheduled" ETA pill, the ML
/// "Predicted" pill (line-tinted) when the predictor is active, a delay
/// warning icon, and the delay-status caption.
struct ArrivalRow: View {
    let arrival: Arrival
    let line: CTALine?

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            VStack(alignment: .leading, spacing: 7) {
                destinationLine
                pills
                if let status = arrival.delayStatus, !status.isEmpty {
                    Text(status)
                        .font(.caption2)
                        .foregroundStyle(Theme.secondaryText)
                }
            }

            Spacer(minLength: 0)

            if let run = arrival.runNumber {
                Text("Run \(run)")
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(Theme.secondaryText)
                    .padding(.top, 3)
            }
        }
        .padding(.vertical, 10)
        .accessibilityElement(children: .combine)
    }

    private var destinationLine: some View {
        HStack(spacing: 6) {
            Image(systemName: "arrow.right")
                .font(.caption.weight(.semibold))
                .foregroundStyle(Theme.secondaryText)
                .accessibilityHidden(true)

            Text(arrival.destination ?? "—")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.8)

            if arrival.isDelayed {
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.yellow)
                    .accessibilityLabel("Delayed")
            }
        }
    }

    private var pills: some View {
        HStack(spacing: 6) {
            ArrivalPill(
                kind: .scheduled,
                label: "Scheduled",
                value: scheduledValue,
                tint: nil
            )

            if let predicted = predictedValue {
                ArrivalPill(
                    kind: .predicted,
                    label: "Predicted",
                    value: predicted,
                    tint: line?.color
                )
            }
        }
    }

    /// The CTA-reported ETA, shown in the bordered "Scheduled" pill.
    private var scheduledValue: String {
        if arrival.isApproaching { return "Now" }
        if let eta = arrival.etaMinutes { return "\(eta) min" }
        return "—"
    }

    /// The ML-adjusted ETA for the tinted "Predicted" pill;
    /// nil hides the pill entirely.
    private var predictedValue: String? {
        guard let predicted = arrival.predictedMinutes else { return nil }
        if arrival.isApproaching || predicted == 0 { return "Now" }
        return "~\(predicted) min"
    }
}

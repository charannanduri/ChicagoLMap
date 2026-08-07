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
    /// When set, each row shows a "Board" button that starts trip tracking.
    var onBoard: ((Arrival, CTALine?) -> Void)? = nil
    /// Station these arrivals belong to — passed to each row for feedback.
    var stationId: Int? = nil

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
                        ArrivalRow(
                            arrival: arrival,
                            line: group.line,
                            onBoard: onBoard.map { cb in { cb(arrival, group.line) } },
                            stationId: stationId
                        )
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
    var onBoard: (() -> Void)? = nil
    /// Station this arrival belongs to — needed to attribute accuracy feedback.
    var stationId: Int? = nil

    @AppStorage(timeFormatDefaultsKey) private var timeFormat: TimeFormat = .relative

    @State private var fbExpanded = false
    @State private var fbDelta = 0
    @State private var fbState: FeedbackState = .idle

    private enum FeedbackState { case idle, sending, done, failed }

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
                if arrival.predictedMinutes != nil {
                    feedbackControl
                }
            }

            Spacer(minLength: 0)

            VStack(alignment: .trailing, spacing: 8) {
                if let run = arrival.runNumber {
                    Text("Run \(run)")
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(Theme.secondaryText)
                }
                if onBoard != nil, arrival.runNumber != nil {
                    boardButton
                }
            }
            .padding(.top, 3)
        }
        .padding(.vertical, 10)
        .accessibilityElement(children: .combine)
    }

    private var boardButton: some View {
        Button {
            onBoard?()
        } label: {
            HStack(spacing: 4) {
                Image(systemName: "figure.wave")
                    .font(.caption2.weight(.bold))
                Text("Board")
                    .font(.caption2.weight(.bold))
            }
            .foregroundStyle(line?.color ?? .white)
            .padding(.horizontal, 10)
            .frame(minHeight: 30)
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .liquidGlassCapsule(interactive: true)
        .accessibilityLabel("Board this train")
    }

    // MARK: Accuracy feedback

    @ViewBuilder
    private var feedbackControl: some View {
        switch fbState {
        case .done:
            Label("Thanks — logged", systemImage: "checkmark.circle.fill")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.green)
        default:
            if fbExpanded {
                HStack(spacing: 8) {
                    Text("Off by")
                        .font(.caption2)
                        .foregroundStyle(Theme.secondaryText)
                    stepButton("minus.circle.fill") { fbDelta = max(-60, fbDelta - 1) }
                    Text(deltaLabel)
                        .font(.caption.weight(.semibold).monospacedDigit())
                        .foregroundStyle(.white)
                        .frame(minWidth: 52)
                    stepButton("plus.circle.fill") { fbDelta = min(60, fbDelta + 1) }
                    Button(action: submitFeedback) {
                        Text(fbState == .sending ? "…" : "Send")
                            .font(.caption2.weight(.bold))
                            .foregroundStyle(line?.color ?? .white)
                            .padding(.horizontal, 10)
                            .frame(minHeight: 28)
                            .contentShape(Capsule())
                    }
                    .buttonStyle(.plain)
                    .liquidGlassCapsule(interactive: true)
                    .disabled(fbState == .sending)
                    if fbState == .failed {
                        Text("Couldn't send")
                            .font(.caption2)
                            .foregroundStyle(.red)
                    }
                }
            } else {
                Button {
                    fbExpanded = true
                } label: {
                    Label("Was our ETA right?", systemImage: "hand.thumbsup")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(Theme.secondaryText)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Rate arrival accuracy")
            }
        }
    }

    /// How far off our prediction was, as the rider reports it.
    private var deltaLabel: String {
        if fbDelta == 0 { return "spot on" }
        let sign = fbDelta > 0 ? "+" : ""
        return "\(sign)\(fbDelta) min"
    }

    private func stepButton(_ icon: String, _ action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.body)
                .foregroundStyle(.white)
                .frame(width: 30, height: 28)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func submitFeedback() {
        Task { @MainActor in
            fbState = .sending
            do {
                try await APIClient.shared.submitFeedback(
                    runNumber: arrival.runNumber,
                    stationId: stationId,
                    route: line?.arrivalsKey,
                    predictedDelayMinutes: arrival.delayMinutes,
                    deltaMinutes: Double(fbDelta)
                )
                fbState = .done
            } catch {
                fbState = .failed
            }
        }
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
        switch timeFormat {
        case .clock:
            if let clock = CTATime.clockString(arrival.scheduledDate) { return clock }
            fallthrough
        case .relative:
            if let eta = arrival.etaMinutes { return "\(eta) min" }
            return "—"
        }
    }

    /// The ML-adjusted ETA for the tinted "Predicted" pill;
    /// nil hides the pill entirely.
    private var predictedValue: String? {
        guard let predicted = arrival.predictedMinutes else { return nil }
        if arrival.isApproaching { return "Now" }
        switch timeFormat {
        case .clock:
            if let clock = CTATime.clockString(arrival.predictedDate) { return clock }
            fallthrough
        case .relative:
            return predicted == 0 ? "Now" : "~\(predicted) min"
        }
    }
}

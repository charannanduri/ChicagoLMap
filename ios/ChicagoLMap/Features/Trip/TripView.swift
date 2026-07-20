//
//  TripView.swift
//  ChicagoLMap
//
//  The live trip timeline shown while riding a tracked train: passed stops in
//  grey with the time the train went by, the next stop highlighted, and the
//  stops ahead with predicted arrival times.
//

import SwiftUI

struct TripView: View {
    @Bindable var model: AppModel
    let onEnd: () -> Void

    @AppStorage(timeFormatDefaultsKey) private var timeFormat: TimeFormat = .relative

    private var trip: TripTracker { model.trip }
    private var accent: Color { trip.line?.color ?? .white }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
                .padding(.horizontal, 20)
                .padding(.top, 22)
                .padding(.bottom, 12)

            content
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .preferredColorScheme(.dark)
    }

    // MARK: - Header

    private var header: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 8) {
                        routeBadge
                        if let run = trip.runNumber {
                            Text("Run \(run)")
                                .font(.caption.monospacedDigit().weight(.semibold))
                                .foregroundStyle(Theme.secondaryText)
                        }
                    }

                    Text(titleText)
                        .font(.title3.bold())
                        .foregroundStyle(.white)
                        .lineLimit(2)
                        .minimumScaleFactor(0.8)

                    if let boarding = trip.boardingStationName {
                        Text("Boarded at \(boarding)")
                            .font(.footnote)
                            .foregroundStyle(Theme.secondaryText)
                    }
                }

                Spacer(minLength: 0)

                endButton
            }

            undergroundNote
        }
    }

    private var routeBadge: some View {
        Text(trip.line?.displayName ?? "Train")
            .font(.caption.weight(.bold))
            .foregroundStyle(trip.line == .yellow ? Color.black.opacity(0.85) : .white)
            .padding(.horizontal, 9)
            .padding(.vertical, 3)
            .background(Capsule().fill(accent))
            .overlay(Capsule().stroke(Color.white.opacity(0.2), lineWidth: 0.5))
    }

    private var titleText: String {
        if let dest = trip.destination { return "to \(dest)" }
        return "On this train"
    }

    private var endButton: some View {
        Button(action: onEnd) {
            Text("End")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.white)
                .padding(.horizontal, 16)
                .frame(minHeight: 34)
                .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .liquidGlassCapsule(interactive: true)
        .accessibilityLabel("End trip")
    }

    private var undergroundNote: some View {
        HStack(spacing: 6) {
            Image(systemName: "wifi.slash")
                .font(.caption2)
            Text("Times come from CTA tracker predictions, so this keeps working underground — accuracy is lower where GPS can't reach.")
                .font(.caption2)
                .fixedSize(horizontal: false, vertical: true)
        }
        .foregroundStyle(Theme.secondaryText)
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(Color.white.opacity(0.05)))
    }

    // MARK: - Content

    @ViewBuilder
    private var content: some View {
        if !trip.stops.isEmpty {
            timeline
        } else if trip.loadFailed {
            message(icon: "wifi.exclamationmark",
                    title: "Couldn't load this train",
                    subtitle: "Check your connection and try again.")
        } else if trip.isLoading {
            loading
        } else {
            message(icon: "tram",
                    title: "This train isn't reporting stops",
                    subtitle: "It may have finished its run. Try boarding again from a station.")
        }
    }

    private var timeline: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                ForEach(Array(trip.stops.enumerated()), id: \.element.id) { index, stop in
                    TripStopRow(
                        stop: stop,
                        accent: accent,
                        timeFormat: timeFormat,
                        isFirst: index == 0,
                        isLast: index == trip.stops.count - 1
                    )
                }
            }
            .padding(.horizontal, 20)
            .padding(.top, 4)
            .padding(.bottom, 28)
        }
        .scrollIndicators(.hidden)
        .animation(.default, value: trip.stops.map(\.id))
    }

    private var loading: some View {
        VStack(spacing: 14) {
            ProgressView()
                .controlSize(.large)
                .tint(.white)
            Text("Finding your train…")
                .font(.footnote)
                .foregroundStyle(Theme.secondaryText)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.bottom, 40)
    }

    private func message(icon: String, title: String, subtitle: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: icon)
                .font(.system(size: 34, weight: .medium))
                .foregroundStyle(Theme.secondaryText)
            Text(title)
                .font(.headline)
                .foregroundStyle(.white)
                .multilineTextAlignment(.center)
            Text(subtitle)
                .font(.footnote)
                .foregroundStyle(Theme.secondaryText)
                .multilineTextAlignment(.center)
        }
        .padding(.horizontal, 32)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.bottom, 40)
    }
}

// MARK: - TripStopRow

private struct TripStopRow: View {
    let stop: TripStop
    let accent: Color
    let timeFormat: TimeFormat
    let isFirst: Bool
    let isLast: Bool

    var body: some View {
        HStack(alignment: .center, spacing: 14) {
            railColumn
            nameColumn
            Spacer(minLength: 8)
            timeColumn
        }
        .frame(minHeight: 52)
        .opacity(stop.status == .passed ? 0.5 : 1.0)
        .accessibilityElement(children: .combine)
    }

    // Vertical rail with a node dot; the continuous stack of rows connects them.
    private var railColumn: some View {
        ZStack {
            VStack(spacing: 0) {
                Rectangle()
                    .fill(lineColor.opacity(isFirst ? 0 : 0.9))
                    .frame(width: 2)
                Rectangle()
                    .fill(lineColor.opacity(isLast ? 0 : 0.9))
                    .frame(width: 2)
            }
            dot
        }
        .frame(width: 22)
    }

    private var dot: some View {
        Group {
            switch stop.status {
            case .current:
                Circle()
                    .fill(accent)
                    .frame(width: 15, height: 15)
                    .overlay(Circle().stroke(Color.white, lineWidth: 2.5))
                    .shadow(color: accent.opacity(0.7), radius: 4)
            case .upcoming:
                Circle()
                    .fill(Theme.background)
                    .frame(width: 12, height: 12)
                    .overlay(Circle().stroke(accent, lineWidth: 2.5))
            case .passed:
                Circle()
                    .fill(Color.gray)
                    .frame(width: 9, height: 9)
            }
        }
    }

    private var lineColor: Color {
        stop.status == .passed ? Color.gray : accent
    }

    private var nameColumn: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(stop.name)
                .font(stop.status == .current ? .subheadline.bold() : .subheadline)
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.8)

            if let subtitle {
                Text(subtitle)
                    .font(.caption2)
                    .foregroundStyle(stop.status == .current ? accent : Theme.secondaryText)
            }
        }
    }

    private var subtitle: String? {
        switch stop.status {
        case .current: return "Next stop"
        case .passed: return "Passed"
        case .upcoming:
            if let status = stop.delayStatus, !status.isEmpty { return status }
            return nil
        }
    }

    private var timeColumn: some View {
        VStack(alignment: .trailing, spacing: 2) {
            if let primary = primaryTime {
                Text(primary)
                    .font(.subheadline.weight(.semibold).monospacedDigit())
                    .foregroundStyle(timeColor)
            }
            if let secondary = secondaryTime {
                Text(secondary)
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(Theme.secondaryText)
                    .strikethrough(stop.predictorActive, color: Theme.secondaryText)
            }
        }
    }

    private var timeColor: Color {
        switch stop.status {
        case .passed: return Theme.secondaryText
        case .current: return accent
        case .upcoming: return .white
        }
    }

    /// The main time shown for a stop — predicted when available, else scheduled.
    private var primaryTime: String? {
        if stop.status == .passed {
            if let observed = CTATime.clockString(stop.observedPassTime) { return observed }
            return "—"
        }

        switch timeFormat {
        case .clock:
            if stop.predictorActive, let predicted = CTATime.clockString(stop.predictedDate) { return predicted }
            if let scheduled = CTATime.clockString(stop.scheduledDate) { return scheduled }
            fallthrough
        case .relative:
            if stop.isApproaching { return "Now" }
            if let minutes = predictedMinutes { return minutes == 0 ? "Now" : "\(minutes) min" }
            if let eta = stop.etaMinutes { return "\(eta) min" }
            return nil
        }
    }

    /// In clock mode, show the plain CTA schedule beneath the prediction.
    private var secondaryTime: String? {
        guard timeFormat == .clock, stop.status != .passed, stop.predictorActive else { return nil }
        guard CTATime.clockString(stop.predictedDate) != nil else { return nil }
        return CTATime.clockString(stop.scheduledDate)
    }

    private var predictedMinutes: Int? {
        guard stop.predictorActive, let delay = stop.delayMinutes else { return nil }
        let eta = Double(stop.etaMinutes ?? 0)
        return max(0, Int((eta + delay).rounded()))
    }
}

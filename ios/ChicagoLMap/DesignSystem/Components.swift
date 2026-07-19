//
//  Components.swift
//  ChicagoLMap
//
//  Reusable design-system components: line filter chips, the live status pill,
//  and the arrival ("Scheduled"/"Predicted") pills. Self-contained — depends
//  only on Theme, Glass, and the CTALine type.
//

import SwiftUI

// MARK: - Shared chip label

private struct ChipLabel: View {
    let text: String
    let textColor: Color

    var body: some View {
        Text(text)
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(textColor)
            .padding(.horizontal, 16)
            .frame(minHeight: 44)
            .contentShape(Capsule())
    }
}

// MARK: - LineChip

/// Filter pill for a single CTA line.
struct LineChip: View {
    let line: CTALine
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            if isSelected {
                ChipLabel(text: line.displayName, textColor: .white)
                    .background(Capsule().fill(line.color.opacity(0.85)))
                    .overlay(Capsule().stroke(Color.white.opacity(0.25), lineWidth: 0.5))
            } else {
                ChipLabel(text: line.displayName, textColor: line.color)
                    .liquidGlassCapsule(interactive: true)
            }
        }
        .buttonStyle(.plain)
        .animation(.spring(response: 0.3, dampingFraction: 0.7), value: isSelected)
        .accessibilityLabel("\(line.displayName) Line")
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }
}

// MARK: - AllLinesChip

/// Filter pill that selects every line at once.
struct AllLinesChip: View {
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            if isSelected {
                ChipLabel(text: "ALL", textColor: Theme.background)
                    .background(Capsule().fill(Color.white.opacity(0.85)))
                    .overlay(Capsule().stroke(Color.white.opacity(0.25), lineWidth: 0.5))
            } else {
                ChipLabel(text: "ALL", textColor: .white)
                    .liquidGlassCapsule(interactive: true)
            }
        }
        .buttonStyle(.plain)
        .animation(.spring(response: 0.3, dampingFraction: 0.7), value: isSelected)
        .accessibilityLabel("All Lines")
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }
}

// MARK: - StatusPill

/// Bottom-center pill: "LIVE · 12:04:31" with a pulsing green dot,
/// or a red dot + "OFFLINE" when the connection is lost.
struct StatusPill: View {
    let lastUpdated: Date?
    let connectionLost: Bool

    private static let timeFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm:ss"
        return formatter
    }()

    var body: some View {
        HStack(spacing: 8) {
            PulsingDot(
                color: connectionLost ? .red : .green,
                isPulsing: !connectionLost
            )
            .id(connectionLost)

            if connectionLost {
                Text("OFFLINE")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.red)
            } else {
                Text(liveText)
                    .font(.caption.weight(.semibold).monospacedDigit())
                    .foregroundStyle(.white)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .liquidGlassCapsule()
        .accessibilityElement(children: .combine)
    }

    private var liveText: String {
        if let lastUpdated {
            return "LIVE · " + Self.timeFormatter.string(from: lastUpdated)
        }
        return "LIVE"
    }
}

/// Small dot that gently pulses (scale + opacity) while live.
private struct PulsingDot: View {
    let color: Color
    let isPulsing: Bool

    @State private var pulsing = false

    var body: some View {
        Circle()
            .fill(color)
            .frame(width: 8, height: 8)
            .scaleEffect(pulsing ? 1.3 : 1.0)
            .opacity(pulsing ? 0.55 : 1.0)
            .onAppear {
                guard isPulsing else { return }
                withAnimation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true)) {
                    pulsing = true
                }
            }
            .accessibilityHidden(true)
    }
}

// MARK: - ArrivalPill

/// "Scheduled 4 min" (bordered) or "Predicted ~6 min" (tinted) pill.
struct ArrivalPill: View {
    enum Kind { case scheduled, predicted }

    let kind: Kind
    let label: String
    let value: String
    let tint: Color?

    var body: some View {
        HStack(spacing: 5) {
            Text(label)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(labelColor)
            Text(value)
                .font(.caption.weight(.bold).monospacedDigit())
                .foregroundStyle(.white)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .background(Capsule().fill(fillColor))
        .overlay(Capsule().stroke(strokeColor, lineWidth: 1))
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(label) \(value)")
    }

    private var labelColor: Color {
        switch kind {
        case .scheduled:
            return Theme.secondaryText
        case .predicted:
            return Color.white.opacity(0.8)
        }
    }

    private var fillColor: Color {
        switch kind {
        case .scheduled:
            return Color.clear
        case .predicted:
            return (tint ?? Color.white).opacity(0.22)
        }
    }

    private var strokeColor: Color {
        switch kind {
        case .scheduled:
            return Theme.cardStroke
        case .predicted:
            return (tint ?? Color.white).opacity(0.45)
        }
    }
}

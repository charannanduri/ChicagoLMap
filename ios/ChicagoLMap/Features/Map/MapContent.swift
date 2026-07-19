import SwiftUI
import MapKit
import CoreLocation

/// Marker for a single live train: a line-colored disc with a heading chevron.
/// Shows a pulsing red ring while the train is reported delayed.
struct TrainMarker: View {
    let train: Train

    @State private var isPulsing = false

    var body: some View {
        ZStack {
            if train.isDelayed {
                Circle()
                    .stroke(Color.red.opacity(isPulsing ? 0.0 : 0.8), lineWidth: 2)
                    .frame(width: 22, height: 22)
                    .scaleEffect(isPulsing ? 1.7 : 1.0)
                    .onAppear {
                        withAnimation(.easeOut(duration: 1.2).repeatForever(autoreverses: false)) {
                            isPulsing = true
                        }
                    }
                    .onDisappear {
                        // Reset so the pulse restarts if the train goes
                        // delayed → on time → delayed again; otherwise the
                        // ring re-appears frozen at its invisible end state.
                        isPulsing = false
                    }
            }

            Circle()
                .fill(train.line.color)
                .overlay(
                    Circle()
                        .strokeBorder(Color.white, lineWidth: 2)
                )
                .frame(width: 22, height: 22)
                .shadow(color: Color.black.opacity(0.4), radius: 3, x: 0, y: 1)

            Image(systemName: "chevron.up")
                .font(.system(size: 10, weight: .bold))
                .foregroundStyle(Color.white)
                .rotationEffect(.degrees(train.heading))
        }
        .accessibilityLabel(accessibilityText)
    }

    private var accessibilityText: String {
        var parts: [String] = ["\(train.line.displayName) Line train"]
        if let destination = train.destinationName {
            parts.append("to \(destination)")
        }
        if train.isDelayed {
            parts.append("delayed")
        }
        return parts.joined(separator: ", ")
    }
}

/// Subtle station dot: small white circle with a line-colored stroke for
/// single-line stations and a gray stroke for transfer stations. The tap
/// target is padded well beyond the visible 10 pt dot.
struct StationDot: View {
    let station: Station

    var body: some View {
        Circle()
            .fill(Color.white.opacity(0.9))
            .overlay(
                Circle()
                    .strokeBorder(strokeColor, lineWidth: 1.5)
            )
            .frame(width: 10, height: 10)
            .frame(width: 30, height: 30)
            .contentShape(Circle())
            .accessibilityLabel("\(station.name) station")
    }

    private var strokeColor: Color {
        if station.lines.count == 1, let line = station.lines.first {
            return line.color
        }
        return Color.gray
    }
}

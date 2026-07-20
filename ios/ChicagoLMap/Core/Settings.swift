//
//  Settings.swift
//  ChicagoLMap
//
//  User preferences and the shared time-formatting utilities used by both the
//  station arrivals and the live trip view.
//

import Foundation

/// UserDefaults key backing the time-format preference (read via @AppStorage).
let timeFormatDefaultsKey = "timeFormat"

/// How arrival/prediction times are presented throughout the app.
enum TimeFormat: String, CaseIterable, Identifiable {
    /// Relative minutes, e.g. "Scheduled 1 min · Predicted 2 min".
    case relative
    /// Wall-clock time, e.g. "Scheduled 4:16 · Predicted 4:17".
    case clock

    var id: String { rawValue }

    var label: String {
        switch self {
        case .relative: return "Minutes"
        case .clock: return "Clock time"
        }
    }

    var example: String {
        switch self {
        case .relative: return "Scheduled 1 min · Predicted 2 min"
        case .clock: return "Scheduled 4:16 · Predicted 4:17"
        }
    }
}

/// Parsing/formatting for CTA timestamps, which are Chicago-local wall-clock
/// strings with no timezone suffix (e.g. "2026-07-19T16:16:00"). Everything is
/// pinned to America/Chicago so times read correctly regardless of device zone.
enum CTATime {
    static let chicago = TimeZone(identifier: "America/Chicago") ?? .current

    private static let parser: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = chicago
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return f
    }()

    private static let clockFormatter: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = chicago
        f.dateFormat = "h:mm"
        return f
    }()

    /// Parse a CTA local timestamp string into a `Date`.
    static func parse(_ string: String?) -> Date? {
        guard let string, !string.isEmpty else { return nil }
        return parser.date(from: string)
    }

    /// Format a `Date` as a Chicago wall-clock time, e.g. "4:16".
    static func clockString(_ date: Date?) -> String? {
        guard let date else { return nil }
        return clockFormatter.string(from: date)
    }
}

//
//  Theme.swift
//  ChicagoLMap
//
//  Design-system color constants matching the website's dark-first palette.
//

import SwiftUI

enum Theme {
    /// App background, #0b0d10 — matches the website.
    static let background = Color(red: 0.043, green: 0.051, blue: 0.063)

    /// Hairline stroke used around glass cards and pills.
    static let cardStroke = Color.white.opacity(0.12)

    /// Secondary/caption text on dark backgrounds.
    static let secondaryText = Color.white.opacity(0.55)

    /// Converts a 24-bit RGB hex value (e.g. `0xC60C30`) to a `Color`.
    /// Design-system internal convenience; `CTALine.color` intentionally does
    /// not use this (it hardcodes `Color(red:green:blue:)` in Models.swift).
    static func color(hex: UInt32) -> Color {
        Color(
            red: Double((hex >> 16) & 0xFF) / 255.0,
            green: Double((hex >> 8) & 0xFF) / 255.0,
            blue: Double(hex & 0xFF) / 255.0
        )
    }
}

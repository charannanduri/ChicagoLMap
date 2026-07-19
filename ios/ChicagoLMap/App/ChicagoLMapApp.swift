//
//  ChicagoLMapApp.swift
//  ChicagoLMap
//
//  App entry point. The whole app is dark-first to match the website,
//  so the color scheme is forced at the window level.
//

import SwiftUI

@main
struct ChicagoLMapApp: App {
    var body: some Scene {
        WindowGroup {
            RootView()
                .preferredColorScheme(.dark)
        }
    }
}

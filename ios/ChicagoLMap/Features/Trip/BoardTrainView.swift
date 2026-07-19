//
//  BoardTrainView.swift
//  ChicagoLMap
//
//  "Riding a train?" entry flow. Uses location to suggest the nearest stations,
//  then lists the trains arriving there so the rider can tap "Board". Location
//  is only a shortcut — picking the station and run by hand is always available,
//  which is what keeps this usable underground.
//

import SwiftUI
import CoreLocation

struct BoardTrainView: View {
    @Bindable var model: AppModel
    let location: LocationProvider
    /// (arrival, line, boarding station name)
    let onBoard: (Arrival, CTALine?, String) -> Void
    let onClose: () -> Void

    @State private var chosen: Station?
    @State private var arrivals: StationArrivals?
    @State private var isLoading = false
    @State private var failed = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
                .padding(.horizontal, 20)
                .padding(.top, 22)
                .padding(.bottom, 12)

            if !nearbyStations.isEmpty {
                stationPicker
                    .padding(.bottom, 6)
            }

            content
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .preferredColorScheme(.dark)
        .onAppear { location.request() }
        .onChange(of: location.coordinate?.latitude) { _, _ in
            if chosen == nil { chosen = nearbyStations.first }
        }
        .task(id: chosen?.id) {
            guard let station = chosen else { return }
            await load(station)
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Riding a train?")
                    .font(.title2.bold())
                    .foregroundStyle(.white)
                Text("Pick the station you boarded at, then tap your train.")
                    .font(.footnote)
                    .foregroundStyle(Theme.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
            Button(action: onClose) {
                Image(systemName: "xmark")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white)
                    .frame(width: 34, height: 34)
                    .contentShape(Circle())
            }
            .buttonStyle(.plain)
            .liquidGlass(in: Circle(), interactive: true)
            .accessibilityLabel("Close")
        }
    }

    // MARK: - Station picker

    private var stationPicker: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(nearbyStations) { station in
                    Button {
                        chosen = station
                    } label: {
                        Text(station.name)
                            .font(.footnote.weight(.semibold))
                            .foregroundStyle(chosen?.id == station.id ? Theme.background : .white)
                            .padding(.horizontal, 14)
                            .frame(minHeight: 38)
                            .contentShape(Capsule())
                            .background {
                                if chosen?.id == station.id {
                                    Capsule().fill(Color.white.opacity(0.9))
                                }
                            }
                    }
                    .buttonStyle(.plain)
                    .liquidGlassCapsule(interactive: chosen?.id != station.id)
                }
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 2)
        }
    }

    // MARK: - Content

    @ViewBuilder
    private var content: some View {
        if location.isDenied && nearbyStations.isEmpty {
            message(icon: "location.slash",
                    title: "Location is off",
                    subtitle: "Turn on location access to find trains near you — or tap a station on the map and use its Board button.")
        } else if chosen == nil {
            waiting("Finding stations near you…")
        } else if let arrivals, hasTrains(arrivals) {
            arrivalsList(arrivals)
        } else if isLoading {
            waiting("Loading trains…")
        } else if failed {
            message(icon: "wifi.exclamationmark",
                    title: "Couldn't load trains",
                    subtitle: "Check your connection and pick a station again.")
        } else {
            message(icon: "tram",
                    title: "No trains right now",
                    subtitle: "Nothing is arriving at this station at the moment.")
        }
    }

    private func arrivalsList(_ arrivals: StationArrivals) -> some View {
        ScrollView {
            GlassGroup(spacing: 12) {
                LazyVStack(alignment: .leading, spacing: 12) {
                    ForEach(arrivals.directions) { group in
                        DirectionSection(group: group, onBoard: { arrival, line in
                            onBoard(arrival, line, chosen?.name ?? arrivals.stationName ?? "Station")
                        })
                    }
                }
            }
            .padding(.horizontal, 20)
            .padding(.top, 4)
            .padding(.bottom, 28)
        }
        .scrollIndicators(.hidden)
    }

    private func waiting(_ text: String) -> some View {
        VStack(spacing: 14) {
            ProgressView().controlSize(.large).tint(.white)
            Text(text)
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

    // MARK: - Helpers

    /// Up to six stations nearest the device, or empty when no fix yet.
    private var nearbyStations: [Station] {
        guard let here = location.coordinate else { return [] }
        let origin = CLLocation(latitude: here.latitude, longitude: here.longitude)
        return model.stations
            .sorted {
                origin.distance(from: CLLocation(latitude: $0.coordinate.latitude, longitude: $0.coordinate.longitude))
                    < origin.distance(from: CLLocation(latitude: $1.coordinate.latitude, longitude: $1.coordinate.longitude))
            }
            .prefix(6)
            .map { $0 }
    }

    private func hasTrains(_ arrivals: StationArrivals) -> Bool {
        arrivals.directions.contains { !$0.trains.isEmpty }
    }

    private func load(_ station: Station) async {
        isLoading = true
        failed = false
        arrivals = nil
        do {
            arrivals = try await APIClient.shared.arrivals(mapid: station.id, count: 12)
        } catch {
            failed = true
        }
        isLoading = false
    }
}

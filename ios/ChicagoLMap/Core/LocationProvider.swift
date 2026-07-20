//
//  LocationProvider.swift
//  ChicagoLMap
//
//  Thin CoreLocation wrapper used to suggest the nearest station when a rider
//  wants to board a train. Location is a convenience only — the underground-safe
//  path is always picking the run by hand, so a denied permission degrades to
//  manual selection rather than blocking anything.
//

import CoreLocation
import Observation

@Observable @MainActor
final class LocationProvider: NSObject, CLLocationManagerDelegate {
    private(set) var coordinate: CLLocationCoordinate2D?
    private(set) var authorization: CLAuthorizationStatus

    @ObservationIgnored private let manager = CLLocationManager()

    override init() {
        authorization = CLLocationManager().authorizationStatus
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
    }

    /// Requests permission (if needed) and a one-shot location fix.
    func request() {
        switch manager.authorizationStatus {
        case .notDetermined:
            manager.requestWhenInUseAuthorization()
        case .authorizedWhenInUse, .authorizedAlways:
            manager.requestLocation()
        default:
            break
        }
    }

    var isDenied: Bool {
        authorization == .denied || authorization == .restricted
    }

    // MARK: CLLocationManagerDelegate (nonisolated; hop back to the main actor)

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        let status = manager.authorizationStatus
        Task { @MainActor in
            self.authorization = status
            if status == .authorizedWhenInUse || status == .authorizedAlways {
                self.manager.requestLocation()
            }
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let last = locations.last else { return }
        let coord = last.coordinate
        Task { @MainActor in
            self.coordinate = coord
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        // Ignore — manual station selection remains available.
    }
}

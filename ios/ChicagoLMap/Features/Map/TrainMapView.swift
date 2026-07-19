import SwiftUI
import MapKit
import CoreLocation

/// Full-bleed live map of the Chicago 'L': route polylines, station dots,
/// and moving train markers. Uses the iOS 17 MapContentBuilder API only.
struct TrainMapView: View {
    @Bindable var model: AppModel

    @State private var position: MapCameraPosition = .region(
        MKCoordinateRegion(
            center: CLLocationCoordinate2D(latitude: 41.8781, longitude: -87.6298),
            span: MKCoordinateSpan(latitudeDelta: 0.35, longitudeDelta: 0.35)
        )
    )

    var body: some View {
        Map(position: $position) {
            // Route polylines for the currently selected lines.
            ForEach(visiblePolylines) { polyline in
                MapPolyline(coordinates: polyline.coordinates)
                    .stroke(polyline.line.color, lineWidth: 3)
            }

            // Subtle station dots; tapping one selects the station on the model.
            ForEach(visibleStations) { station in
                Annotation(station.name, coordinate: station.coordinate, anchor: .center) {
                    StationDot(station: station)
                        .onTapGesture {
                            model.select(station: station)
                        }
                }
                .annotationTitles(.hidden)
            }

            // Train markers, rotated to heading.
            ForEach(model.trains) { train in
                Annotation(train.runNumber ?? "Train", coordinate: train.coordinate, anchor: .center) {
                    TrainMarker(train: train)
                }
                .annotationTitles(.hidden)
            }
        }
        .mapStyle(.standard(pointsOfInterest: .excludingAll))
        // Trains are Equatable on id + lat/lon + heading + isDelayed, so markers
        // glide smoothly between 15 s polls.
        .animation(.default, value: model.trains)
        .ignoresSafeArea()
    }

    private var visiblePolylines: [RoutePolyline] {
        model.polylines.filter { model.selectedLines.contains($0.line) }
    }

    private var visibleStations: [Station] {
        model.stations.filter { !$0.lines.isDisjoint(with: model.selectedLines) }
    }
}

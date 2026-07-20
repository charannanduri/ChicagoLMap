import Foundation
import CoreLocation

// MARK: - APIClient

struct APIClient: Sendable {
    static let shared = APIClient()

    var baseURL: URL = URL(string: "https://chicagolmap.onrender.com")!

    // MARK: Public endpoints

    /// GET /api/trains/{route} — live positions for one line.
    /// Trains missing a coordinate are dropped.
    func trains(for line: CTALine) async throws -> [Train] {
        let url = baseURL.appending(path: "api/trains/\(line.apiKey)")
        let response: TrainsResponse = try await fetch(url)
        return response.trains.compactMap { dto in
            guard let lat = dto.lat, let lon = dto.lon else { return nil }
            return Train(
                id: dto.runNumber ?? UUID().uuidString,
                line: line,
                coordinate: CLLocationCoordinate2D(latitude: lat, longitude: lon),
                heading: dto.heading ?? 0,
                runNumber: dto.runNumber,
                nextStationName: dto.nextStaName,
                destinationName: dto.destName,
                isApproaching: dto.isApproaching,
                isDelayed: dto.isDelayed
            )
        }
    }

    /// Fetches all 8 lines' stop GeoJSON concurrently and merges the features
    /// by `mapid` so a transfer station becomes one `Station` with several lines.
    func allStations() async throws -> [Station] {
        let records = try await withThrowingTaskGroup(of: [StopRecord].self) { group -> [StopRecord] in
            for line in CTALine.allCases {
                group.addTask {
                    try await self.stops(for: line)
                }
            }
            var collected: [StopRecord] = []
            for try await batch in group {
                collected.append(contentsOf: batch)
            }
            return collected
        }

        var merged: [Int: Station] = [:]
        for record in records {
            if var existing = merged[record.mapid] {
                existing.lines.insert(record.line)
                merged[record.mapid] = existing
            } else {
                merged[record.mapid] = Station(
                    id: record.mapid,
                    name: record.name,
                    coordinate: CLLocationCoordinate2D(latitude: record.latitude, longitude: record.longitude),
                    lines: [record.line]
                )
            }
        }
        return merged.values.sorted { $0.name < $1.name }
    }

    /// GET /api/geojson/routes/all — one `RoutePolyline` per LineString
    /// (MultiLineString features are split into one polyline per part).
    func routePolylines() async throws -> [RoutePolyline] {
        let url = baseURL.appending(path: "api/geojson/routes/all")
        let collection: RouteFeatureCollection = try await fetch(url)

        var result: [RoutePolyline] = []
        var partCounts: [CTALine: Int] = [:]
        for feature in collection.features {
            guard
                let routeKey = feature.properties?.route,
                let line = CTALine(apiKey: routeKey),
                let geometry = feature.geometry
            else { continue }

            for part in geometry.lineStrings {
                let coordinates = part.compactMap { pair -> CLLocationCoordinate2D? in
                    guard pair.count >= 2 else { return nil }
                    return CLLocationCoordinate2D(latitude: pair[1], longitude: pair[0])
                }
                guard coordinates.count >= 2 else { continue }
                let index = partCounts[line, default: 0]
                partCounts[line] = index + 1
                result.append(RoutePolyline(id: "\(line.rawValue)-\(index)", line: line, coordinates: coordinates))
            }
        }
        return result
    }

    /// GET /api/station/{mapid}/arrivals?n={count}
    func arrivals(mapid: Int, count: Int) async throws -> StationArrivals {
        let url = baseURL
            .appending(path: "api/station/\(mapid)/arrivals")
            .appending(queryItems: [URLQueryItem(name: "n", value: String(count))])
        return try await fetch(url)
    }

    /// GET /api/run/{run}/follow — a train's upcoming stops with ML predictions.
    func runFollow(runNumber: String) async throws -> RunFollow {
        let url = baseURL.appending(path: "api/run/\(runNumber)/follow")
        return try await fetch(url)
    }

    // MARK: Private helpers

    private func stops(for line: CTALine) async throws -> [StopRecord] {
        let url = baseURL.appending(path: "api/geojson/stops/\(line.apiKey)")
        let collection: StopFeatureCollection = try await fetch(url)
        return collection.features.compactMap { feature in
            guard
                let mapid = feature.properties?.mapid,
                let coordinates = feature.geometry?.coordinates,
                coordinates.count >= 2
            else { return nil }
            return StopRecord(
                mapid: mapid,
                name: feature.properties?.name ?? "Station",
                latitude: coordinates[1],
                longitude: coordinates[0],
                line: line
            )
        }
    }

    private func fetch<T: Decodable>(_ url: URL) async throws -> T {
        var request = URLRequest(url: url)
        request.timeoutInterval = 30
        let (data, response) = try await URLSession.shared.data(for: request)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw URLError(.badServerResponse)
        }
        return try JSONDecoder().decode(T.self, from: data)
    }
}

// MARK: - Trains DTOs

private struct TrainsResponse: Decodable {
    let trains: [TrainDTO]

    private enum CodingKeys: String, CodingKey {
        case trains
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        trains = try container.decodeIfPresent([TrainDTO].self, forKey: .trains) ?? []
    }
}

private struct TrainDTO: Decodable {
    let lat: Double?
    let lon: Double?
    let heading: Double?
    let runNumber: String?
    let nextStaName: String?
    let destName: String?
    let isApproaching: Bool
    let isDelayed: Bool

    private enum CodingKeys: String, CodingKey {
        case lat
        case lon
        case heading
        case runNumber = "run_number"
        case nextStaName = "next_sta_name"
        case destName = "dest_name"
        case isApproaching = "is_approaching"
        case isDelayed = "is_delayed"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        lat = try container.decodeIfPresent(Double.self, forKey: .lat)
        lon = try container.decodeIfPresent(Double.self, forKey: .lon)

        if let doubleValue = try? container.decode(Double.self, forKey: .heading) {
            heading = doubleValue
        } else if let stringValue = try? container.decode(String.self, forKey: .heading) {
            heading = Double(stringValue)
        } else {
            heading = nil
        }

        if let stringValue = try? container.decode(String.self, forKey: .runNumber) {
            runNumber = stringValue
        } else if let intValue = try? container.decode(Int.self, forKey: .runNumber) {
            runNumber = String(intValue)
        } else {
            runNumber = nil
        }

        nextStaName = try container.decodeIfPresent(String.self, forKey: .nextStaName)
        destName = try container.decodeIfPresent(String.self, forKey: .destName)
        isApproaching = try container.decodeIfPresent(Bool.self, forKey: .isApproaching) ?? false
        isDelayed = try container.decodeIfPresent(Bool.self, forKey: .isDelayed) ?? false
    }
}

// MARK: - Stop GeoJSON DTOs

private struct StopRecord: Sendable {
    let mapid: Int
    let name: String
    let latitude: Double
    let longitude: Double
    let line: CTALine
}

private struct StopFeatureCollection: Decodable {
    let features: [StopFeature]

    private enum CodingKeys: String, CodingKey {
        case features
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        features = try container.decodeIfPresent([StopFeature].self, forKey: .features) ?? []
    }
}

private struct StopFeature: Decodable {
    let properties: StopProperties?
    let geometry: PointGeometry?

    private enum CodingKeys: String, CodingKey {
        case properties
        case geometry
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        properties = try container.decodeIfPresent(StopProperties.self, forKey: .properties)
        geometry = try container.decodeIfPresent(PointGeometry.self, forKey: .geometry)
    }
}

private struct StopProperties: Decodable {
    let name: String?
    let mapid: Int?

    private enum CodingKeys: String, CodingKey {
        case name
        case mapid
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        name = try container.decodeIfPresent(String.self, forKey: .name)
        if let intValue = try? container.decode(Int.self, forKey: .mapid) {
            mapid = intValue
        } else if let doubleValue = try? container.decode(Double.self, forKey: .mapid) {
            mapid = Int(doubleValue)
        } else if let stringValue = try? container.decode(String.self, forKey: .mapid) {
            mapid = Int(stringValue)
        } else {
            mapid = nil
        }
    }
}

private struct PointGeometry: Decodable {
    let coordinates: [Double]?

    private enum CodingKeys: String, CodingKey {
        case coordinates
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        coordinates = try? container.decodeIfPresent([Double].self, forKey: .coordinates)
    }
}

// MARK: - Route GeoJSON DTOs

private struct RouteFeatureCollection: Decodable {
    let features: [RouteFeature]

    private enum CodingKeys: String, CodingKey {
        case features
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        features = try container.decodeIfPresent([RouteFeature].self, forKey: .features) ?? []
    }
}

private struct RouteFeature: Decodable {
    let properties: RouteProperties?
    let geometry: LineGeometry?

    private enum CodingKeys: String, CodingKey {
        case properties
        case geometry
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        properties = try container.decodeIfPresent(RouteProperties.self, forKey: .properties)
        geometry = try container.decodeIfPresent(LineGeometry.self, forKey: .geometry)
    }
}

private struct RouteProperties: Decodable {
    let route: String?

    private enum CodingKeys: String, CodingKey {
        case route
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        route = try container.decodeIfPresent(String.self, forKey: .route)
    }
}

/// Normalizes a GeoJSON `LineString` or `MultiLineString` geometry to a list
/// of line-string coordinate arrays (`[[lon, lat], ...]` each).
private struct LineGeometry: Decodable {
    let lineStrings: [[[Double]]]

    private enum CodingKeys: String, CodingKey {
        case type
        case coordinates
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let type = (try? container.decode(String.self, forKey: .type)) ?? ""
        if type == "MultiLineString" {
            lineStrings = (try? container.decode([[[Double]]].self, forKey: .coordinates)) ?? []
        } else if let single = try? container.decode([[Double]].self, forKey: .coordinates) {
            lineStrings = [single]
        } else if let multi = try? container.decode([[[Double]]].self, forKey: .coordinates) {
            lineStrings = multi
        } else {
            lineStrings = []
        }
    }
}

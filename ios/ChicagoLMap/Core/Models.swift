import SwiftUI
import CoreLocation

// MARK: - CTALine

enum CTALine: String, CaseIterable, Identifiable, Codable, Hashable {
    case red, blue, green, brown, orange, purple, pink, yellow

    var id: String { rawValue }

    /// Lowercase key used by the map/trains/geojson endpoints.
    var apiKey: String {
        switch self {
        case .red: return "red"
        case .blue: return "blue"
        case .green: return "g"
        case .brown: return "brn"
        case .orange: return "o"
        case .purple: return "p"
        case .pink: return "pnk"
        case .yellow: return "y"
        }
    }

    /// Route key style used by the arrivals endpoint (`directions[].route`).
    var arrivalsKey: String {
        switch self {
        case .red: return "Red"
        case .blue: return "Blue"
        case .green: return "G"
        case .brown: return "Brn"
        case .orange: return "Org"
        case .purple: return "P"
        case .pink: return "Pink"
        case .yellow: return "Y"
        }
    }

    var displayName: String {
        switch self {
        case .red: return "Red"
        case .blue: return "Blue"
        case .green: return "Green"
        case .brown: return "Brown"
        case .orange: return "Orange"
        case .purple: return "Purple"
        case .pink: return "Pink"
        case .yellow: return "Yellow"
        }
    }

    var color: Color {
        switch self {
        case .red: return Color(red: 198.0 / 255.0, green: 12.0 / 255.0, blue: 48.0 / 255.0) // #c60c30
        case .blue: return Color(red: 0.0 / 255.0, green: 161.0 / 255.0, blue: 222.0 / 255.0) // #00a1de
        case .green: return Color(red: 0.0 / 255.0, green: 155.0 / 255.0, blue: 58.0 / 255.0) // #009b3a
        case .brown: return Color(red: 98.0 / 255.0, green: 54.0 / 255.0, blue: 27.0 / 255.0) // #62361b
        case .orange: return Color(red: 249.0 / 255.0, green: 70.0 / 255.0, blue: 28.0 / 255.0) // #f9461c
        case .purple: return Color(red: 82.0 / 255.0, green: 35.0 / 255.0, blue: 152.0 / 255.0) // #522398
        case .pink: return Color(red: 226.0 / 255.0, green: 126.0 / 255.0, blue: 166.0 / 255.0) // #e27ea6
        case .yellow: return Color(red: 249.0 / 255.0, green: 227.0 / 255.0, blue: 0.0 / 255.0) // #f9e300
        }
    }

    init?(apiKey: String) {
        let key = apiKey.lowercased()
        guard let match = CTALine.allCases.first(where: { $0.apiKey == key }) else {
            return nil
        }
        self = match
    }

    init?(arrivalsKey: String) {
        guard let match = CTALine.allCases.first(where: {
            $0.arrivalsKey.caseInsensitiveCompare(arrivalsKey) == .orderedSame
        }) else {
            return nil
        }
        self = match
    }
}

// MARK: - Train

struct Train: Identifiable, Hashable {
    let id: String
    let line: CTALine
    let coordinate: CLLocationCoordinate2D
    let heading: Double
    let runNumber: String?
    let nextStationName: String?
    let destinationName: String?
    let isApproaching: Bool
    let isDelayed: Bool

    static func == (lhs: Train, rhs: Train) -> Bool {
        lhs.id == rhs.id
            && lhs.coordinate.latitude == rhs.coordinate.latitude
            && lhs.coordinate.longitude == rhs.coordinate.longitude
            && lhs.heading == rhs.heading
            && lhs.isDelayed == rhs.isDelayed
    }

    func hash(into hasher: inout Hasher) {
        hasher.combine(id)
        hasher.combine(coordinate.latitude)
        hasher.combine(coordinate.longitude)
        hasher.combine(heading)
        hasher.combine(isDelayed)
    }
}

// MARK: - Station

struct Station: Identifiable, Hashable {
    let id: Int
    let name: String
    let coordinate: CLLocationCoordinate2D
    var lines: Set<CTALine>

    static func == (lhs: Station, rhs: Station) -> Bool {
        lhs.id == rhs.id
    }

    func hash(into hasher: inout Hasher) {
        hasher.combine(id)
    }
}

// MARK: - RoutePolyline

struct RoutePolyline: Identifiable {
    let id: String
    let line: CTALine
    let coordinates: [CLLocationCoordinate2D]
}

// MARK: - StationArrivals

struct StationArrivals: Decodable {
    let mapid: Int
    let stationName: String?
    let directions: [DirectionGroup]

    private enum CodingKeys: String, CodingKey {
        case mapid
        case stationName = "station_name"
        case directions
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        mapid = try container.decodeIfPresent(Int.self, forKey: .mapid) ?? 0
        stationName = try container.decodeIfPresent(String.self, forKey: .stationName)
        directions = try container.decodeIfPresent([DirectionGroup].self, forKey: .directions) ?? []
    }
}

// MARK: - DirectionGroup

struct DirectionGroup: Decodable, Identifiable {
    let route: String
    let directionLabel: String
    let trains: [Arrival]

    var id: String { route + directionLabel }
    var line: CTALine? { CTALine(arrivalsKey: route) }

    private enum CodingKeys: String, CodingKey {
        case route
        case directionLabel = "direction_label"
        case trains
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        route = try container.decodeIfPresent(String.self, forKey: .route) ?? ""
        directionLabel = try container.decodeIfPresent(String.self, forKey: .directionLabel) ?? ""
        trains = try container.decodeIfPresent([Arrival].self, forKey: .trains) ?? []
    }
}

// MARK: - Arrival

struct Arrival: Decodable, Identifiable {
    let runNumber: String?
    let destination: String?
    let etaMinutes: Int?
    let isApproaching: Bool
    let isScheduled: Bool
    let isDelayed: Bool
    let delayMinutes: Double?
    let delayStatus: String?
    let p10Minutes: Double?
    let p90Minutes: Double?
    let predictorActive: Bool

    var id: String { (runNumber ?? "?") + (destination ?? "") }

    /// ETA adjusted by the ML delay prediction, clamped to zero.
    /// Non-nil only when the predictor is active and produced a delay estimate.
    var predictedMinutes: Int? {
        guard predictorActive, let delayMinutes else { return nil }
        let eta = Double(etaMinutes ?? 0)
        return max(0, Int((eta + delayMinutes).rounded()))
    }

    private enum CodingKeys: String, CodingKey {
        case runNumber = "run_number"
        case destination
        case etaMinutes = "eta_minutes"
        case isApproaching = "is_approaching"
        case isScheduled = "is_scheduled"
        case isDelayed = "is_delayed"
        case delayMinutes = "delay_minutes"
        case delayStatus = "delay_status"
        case p10Minutes = "p10_minutes"
        case p90Minutes = "p90_minutes"
        case predictorActive = "predictor_active"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)

        if let stringValue = try? container.decode(String.self, forKey: .runNumber) {
            runNumber = stringValue
        } else if let intValue = try? container.decode(Int.self, forKey: .runNumber) {
            runNumber = String(intValue)
        } else {
            runNumber = nil
        }

        destination = try container.decodeIfPresent(String.self, forKey: .destination)

        if let intValue = try? container.decode(Int.self, forKey: .etaMinutes) {
            etaMinutes = intValue
        } else if let doubleValue = try? container.decode(Double.self, forKey: .etaMinutes) {
            etaMinutes = Int(doubleValue.rounded())
        } else {
            etaMinutes = nil
        }

        isApproaching = try container.decodeIfPresent(Bool.self, forKey: .isApproaching) ?? false
        isScheduled = try container.decodeIfPresent(Bool.self, forKey: .isScheduled) ?? false
        isDelayed = try container.decodeIfPresent(Bool.self, forKey: .isDelayed) ?? false
        delayMinutes = try container.decodeIfPresent(Double.self, forKey: .delayMinutes)
        delayStatus = try container.decodeIfPresent(String.self, forKey: .delayStatus)
        p10Minutes = try container.decodeIfPresent(Double.self, forKey: .p10Minutes)
        p90Minutes = try container.decodeIfPresent(Double.self, forKey: .p90Minutes)
        predictorActive = try container.decodeIfPresent(Bool.self, forKey: .predictorActive) ?? false
    }
}

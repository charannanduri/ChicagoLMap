//
//  TripModels.swift
//  ChicagoLMap
//
//  Types for live trip tracking: the decoded /api/run/<run>/follow response and
//  the per-stop display model the trip timeline renders.
//

import Foundation

// MARK: - RunFollow (decoded API response)

struct RunFollow: Decodable {
    let runNumber: String?
    let route: String?
    let destination: String?
    let stops: [RunStop]

    var line: CTALine? { route.flatMap { CTALine(arrivalsKey: $0) } }

    private enum CodingKeys: String, CodingKey {
        case runNumber = "run_number"
        case route
        case destination
        case stops
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        runNumber = try container.decodeIfPresent(String.self, forKey: .runNumber)
        route = try container.decodeIfPresent(String.self, forKey: .route)
        destination = try container.decodeIfPresent(String.self, forKey: .destination)
        stops = try container.decodeIfPresent([RunStop].self, forKey: .stops) ?? []
    }
}

struct RunStop: Decodable {
    let stationId: Int?
    let stationName: String?
    let etaMinutes: Int?
    let arrivalTimeRaw: String?
    let predictedArrivalTimeRaw: String?
    let delayMinutes: Double?
    let delayStatus: String?
    let predictorActive: Bool
    let isApproaching: Bool
    let isDelayed: Bool

    var scheduledDate: Date? { CTATime.parse(arrivalTimeRaw) }
    var predictedDate: Date? { CTATime.parse(predictedArrivalTimeRaw) }

    private enum CodingKeys: String, CodingKey {
        case stationId = "station_id"
        case stationName = "station_name"
        case etaMinutes = "eta_minutes"
        case arrivalTimeRaw = "arrival_time"
        case predictedArrivalTimeRaw = "predicted_arrival_time"
        case delayMinutes = "delay_minutes"
        case delayStatus = "delay_status"
        case predictorActive = "predictor_active"
        case isApproaching = "is_approaching"
        case isDelayed = "is_delayed"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        if let intValue = try? container.decode(Int.self, forKey: .stationId) {
            stationId = intValue
        } else if let stringValue = try? container.decode(String.self, forKey: .stationId) {
            stationId = Int(stringValue)
        } else {
            stationId = nil
        }
        stationName = try container.decodeIfPresent(String.self, forKey: .stationName)
        if let intValue = try? container.decode(Int.self, forKey: .etaMinutes) {
            etaMinutes = intValue
        } else if let doubleValue = try? container.decode(Double.self, forKey: .etaMinutes) {
            etaMinutes = Int(doubleValue.rounded())
        } else {
            etaMinutes = nil
        }
        arrivalTimeRaw = try container.decodeIfPresent(String.self, forKey: .arrivalTimeRaw)
        predictedArrivalTimeRaw = try container.decodeIfPresent(String.self, forKey: .predictedArrivalTimeRaw)
        delayMinutes = try container.decodeIfPresent(Double.self, forKey: .delayMinutes)
        delayStatus = try container.decodeIfPresent(String.self, forKey: .delayStatus)
        predictorActive = try container.decodeIfPresent(Bool.self, forKey: .predictorActive) ?? false
        isApproaching = try container.decodeIfPresent(Bool.self, forKey: .isApproaching) ?? false
        isDelayed = try container.decodeIfPresent(Bool.self, forKey: .isDelayed) ?? false
    }
}

// MARK: - TripStop (display model)

/// One stop on the tracked trip's timeline.
struct TripStop: Identifiable {
    enum Status {
        case passed     // train has already gone by (grey)
        case current    // the next stop the train will reach
        case upcoming   // further ahead
    }

    let stationId: Int
    let name: String
    var etaMinutes: Int?
    var scheduledDate: Date?
    var predictedDate: Date?
    var delayMinutes: Double?
    var delayStatus: String?
    var predictorActive: Bool
    var isApproaching: Bool
    var status: Status
    /// When the train was observed to pass this stop (set once it drops off the
    /// upcoming list). Approximate — the poll interval bounds its accuracy.
    var observedPassTime: Date?

    var id: Int { stationId }
}

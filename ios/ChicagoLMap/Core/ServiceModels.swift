//
//  ServiceModels.swift
//  ChicagoLMap
//
//  Types for CTA service alerts (from /api/alerts).
//

import Foundation

struct ServiceAlert: Decodable, Identifiable {
    let id: String
    let headline: String
    let description: String
    let impact: String
    let severity: Int
    let routes: [String]   // API keys: red, blue, g, brn, o, p, pnk, y
    let url: String

    /// CTA lines this alert affects (empty = system-wide).
    var lines: [CTALine] {
        routes.compactMap { CTALine(apiKey: $0) }
    }

    private enum CodingKeys: String, CodingKey {
        case id, headline, description, impact, severity, routes, url
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decodeIfPresent(String.self, forKey: .id) ?? UUID().uuidString
        headline = try c.decodeIfPresent(String.self, forKey: .headline) ?? ""
        description = try c.decodeIfPresent(String.self, forKey: .description) ?? ""
        impact = try c.decodeIfPresent(String.self, forKey: .impact) ?? ""
        if let intValue = try? c.decode(Int.self, forKey: .severity) {
            severity = intValue
        } else if let strValue = try? c.decode(String.self, forKey: .severity) {
            severity = Int(strValue) ?? 0
        } else {
            severity = 0
        }
        routes = try c.decodeIfPresent([String].self, forKey: .routes) ?? []
        url = try c.decodeIfPresent(String.self, forKey: .url) ?? ""
    }
}

struct AlertsResponse: Decodable {
    let alerts: [ServiceAlert]

    private enum CodingKeys: String, CodingKey { case alerts }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        alerts = try c.decodeIfPresent([ServiceAlert].self, forKey: .alerts) ?? []
    }
}

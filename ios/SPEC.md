# Chicago L Map — iOS App Spec

Native SwiftUI iOS app for the Chicago 'L' live map + ML delay predictions.
Backend: the existing Flask API at `https://chicagolmap.onrender.com`.

- **Deployment target: iOS 17.0**, built with Xcode 26 (iOS 26 SDK).
- **Liquid Glass** (iOS 26 design language) everywhere it's available, with
  `.ultraThinMaterial` fallbacks behind `if #available(iOS 26.0, *)` gates.
- Dark-first design matching the website (`#0b0d10` background, white text).
- Swift 5 language mode. `@Observable` (Observation framework), async/await,
  no third-party dependencies.

## Directory layout

```
ios/
  project.yml                     ← XcodeGen spec (already written)
  ChicagoLMap/
    App/ChicagoLMapApp.swift      ← agent E
    App/RootView.swift            ← agent E
    Core/Models.swift             ← agent A
    Core/APIClient.swift          ← agent A
    Core/AppModel.swift           ← agent A
    DesignSystem/Theme.swift      ← agent D
    DesignSystem/Glass.swift      ← agent D
    DesignSystem/Components.swift ← agent D
    Features/Map/TrainMapView.swift        ← agent B
    Features/Map/MapContent.swift          ← agent B
    Features/Station/StationSheet.swift    ← agent C
    Features/Station/ArrivalRow.swift      ← agent C
    Resources/Assets.xcassets     ← already written (AppIcon, AccentColor)
```

Each agent writes ONLY its own files. All shared symbols are specified below —
implement them EXACTLY as declared so the modules link.

## Backend API contract

### GET /api/trains/{route}
`route` ∈ `red blue g brn o p pnk y` (lowercase). Response:

```json
{
  "route": "red",
  "position_source": "gps",        // or "schedule"
  "train_count": 12,
  "trains": [
    {
      "lat": 41.9, "lon": -87.6,   // may be null → drop such trains
      "heading": 180,               // degrees, 0 = north
      "run_number": "812",
      "next_sta_id": 40900,         // nullable
      "next_sta_name": "Howard",    // nullable
      "is_approaching": true,
      "is_delayed": false,
      "dest_sta_id": 40900,         // nullable
      "dest_name": "Howard"         // nullable
    }
  ]
}
```

### GET /api/geojson/stops/{route}
GeoJSON `FeatureCollection` of `Point` features:
`properties: {name: String, address: String, route: String(lowercase key), mapid: Int?}`
`geometry.coordinates = [lon, lat]`. Features with `mapid == null` are dropped.
The same physical station appears once per line — merge by `mapid` into one
`Station` with a set of lines.

### GET /api/geojson/routes/{route}  (use `all`)
GeoJSON `FeatureCollection` of `LineString` features,
`properties: {route: String(lowercase key)}`. Split MultiLineString if present.

### GET /api/station/{mapid}/arrivals?n=12
```json
{
  "mapid": 40900,
  "station_name": "Howard",
  "as_of": "2026-07-19T01:00:00+00:00",
  "directions": [
    {
      "route": "Red",              // NOTE: arrivals-style key, see CTALine below
      "direction_label": "toward 95th/Dan Ryan",
      "trains": [
        {
          "run_number": "812",
          "destination": "95th/Dan Ryan",
          "eta_minutes": 4,          // Int?, null possible
          "arrival_time": "...",     // ISO8601, unused
          "is_approaching": false,
          "is_scheduled": false,
          "is_delayed": false,
          "delay_minutes": 1.4,      // Double?, ML prediction
          "delay_status": "On Time", // display string, e.g. "2 min late"
          "p10_minutes": -0.5,       // Double?
          "p90_minutes": 3.2,        // Double?
          "predictor_active": true
        }
      ]
    }
  ]
}
```

Show the ML "Predicted" pill when `predictor_active && delay_minutes != nil`.
Predicted minutes = `max(0, round(eta_minutes + delay_minutes))`, or "Now" when
`is_approaching`.

## Shared Swift symbols (exact signatures)

### Core/Models.swift (agent A)

```swift
enum CTALine: String, CaseIterable, Identifiable, Codable, Hashable {
    case red, blue, green, brown, orange, purple, pink, yellow
    var id: String { rawValue }
    var apiKey: String        // "red","blue","g","brn","o","p","pnk","y"
    var arrivalsKey: String   // "Red","Blue","G","Brn","Org","P","Pink","Y"
    var displayName: String   // "Red","Blue","Green","Brown","Orange","Purple","Pink","Yellow"
    var color: Color          // Theme.swift exposes nothing here; implement with Color(red:green:blue:) hex values below
    init?(apiKey: String)     // lowercase key lookup
    init?(arrivalsKey: String)
}
```

Line colors (from the website): Red `#c60c30`, Blue `#00a1de`, Green `#009b3a`,
Brown `#62361b`, Orange `#f9461c`, Purple `#522398`, Pink `#e27ea6`, Yellow `#f9e300`.

```swift
struct Train: Identifiable, Hashable {
    let id: String            // run_number, or UUID string fallback when nil
    let line: CTALine
    let coordinate: CLLocationCoordinate2D
    let heading: Double
    let runNumber: String?
    let nextStationName: String?
    let destinationName: String?
    let isApproaching: Bool
    let isDelayed: Bool
}
// Hashable/Equatable: implement manually (CLLocationCoordinate2D isn't Hashable) —
// hash/compare id + lat/lon + heading + isDelayed.

struct Station: Identifiable, Hashable {
    let id: Int               // mapid
    let name: String
    let coordinate: CLLocationCoordinate2D
    var lines: Set<CTALine>
    // Hashable/Equatable on id only.
}

struct RoutePolyline: Identifiable {
    let id: String            // "\(line.rawValue)-\(index)"
    let line: CTALine
    let coordinates: [CLLocationCoordinate2D]
}

struct StationArrivals: Decodable {
    let mapid: Int
    let stationName: String?
    let directions: [DirectionGroup]
}

struct DirectionGroup: Decodable, Identifiable {
    let route: String          // arrivalsKey style
    let directionLabel: String
    let trains: [Arrival]
    var id: String { route + directionLabel }
    var line: CTALine? { CTALine(arrivalsKey: route) }
}

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
    var predictedMinutes: Int? // max(0, round(Double(etaMinutes ?? 0) + delay)) when predictorActive && delayMinutes != nil, else nil
}
```

All Decodable structs use explicit `CodingKeys` mapping snake_case JSON keys.
Decode defensively: every field that could be null in JSON is optional, with
`decodeIfPresent`. Booleans default to `false` when missing.

### Core/APIClient.swift (agent A)

```swift
struct APIClient: Sendable {
    static let shared = APIClient()
    var baseURL: URL          // https://chicagolmap.onrender.com

    func trains(for line: CTALine) async throws -> [Train]
    func allStations() async throws -> [Station]      // fetches all 8 lines' stops concurrently (task group), merges by mapid
    func routePolylines() async throws -> [RoutePolyline]  // /api/geojson/routes/all
    func arrivals(mapid: Int, count: Int) async throws -> StationArrivals
}
```

GeoJSON parsing: hand-rolled Decodable structs (FeatureCollection/Feature/
geometry with `type` + `coordinates` as `[[Double]]` for LineString and
`[Double]` for Point). Handle `MultiLineString` (`[[[Double]]]`) by emitting
one RoutePolyline per part: decode coordinates as a JSON value enum or try
LineString first, then MultiLineString.

### Core/AppModel.swift (agent A)

```swift
@Observable @MainActor
final class AppModel {
    var selectedLines: Set<CTALine>        // starts with all 8
    var trains: [Train]                    // flattened, only selected lines
    var stations: [Station]
    var polylines: [RoutePolyline]
    var selectedStation: Station?
    var arrivals: StationArrivals?
    var arrivalsError: Bool
    var isLoadingArrivals: Bool
    var lastUpdated: Date?
    var isRefreshing: Bool
    var connectionLost: Bool               // true when the last refresh failed

    func start() async                     // loads stations+polylines once, then begins polling
    func refreshTrains() async             // fetch trains for selected lines concurrently
    func toggle(_ line: CTALine)           // update selection, drop/add trains, trigger refresh
    func selectAllLines()
    var allSelected: Bool { get }
    func select(station: Station?)         // nil clears; non-nil loads arrivals
    func refreshArrivals() async
}
```

Polling: 15 s `Task.sleep` loop started from `start()`; guard against overlap.
Arrivals auto-refresh every 30 s while a station is selected (loop inside
`select(station:)`'s task, cancelled on deselect — keep a `Task<Void, Never>?`
handle). Station/polyline failures retry once after 3 s, then surface
`connectionLost`.

### DesignSystem (agent D)

`Theme.swift`:
```swift
enum Theme {
    static let background = Color(red: 0.043, green: 0.051, blue: 0.063)  // #0b0d10
    static let cardStroke = Color.white.opacity(0.12)
    static let secondaryText = Color.white.opacity(0.55)
    static func color(hex: UInt32) -> Color    // convenience used by CTALine.color? NO —
    // CTALine.color lives in Models.swift and hardcodes Color(red:green:blue:) values.
    // Theme.color(hex:) exists for design-system internal use only.
}
```

`Glass.swift` — THE Liquid Glass abstraction used by every other view:
```swift
struct LiquidGlassModifier<S: Shape>: ViewModifier { ... }

extension View {
    /// iOS 26: real .glassEffect(...); earlier: .ultraThinMaterial fill + subtle stroke.
    func liquidGlass(in shape: some Shape, interactive: Bool = false, tint: Color? = nil) -> some View
    func liquidGlassCapsule(interactive: Bool = false, tint: Color? = nil) -> some View
}

/// Groups glass shapes so iOS 26 can morph/blend them; passthrough VStack-free
/// wrapper on earlier OS versions.
struct GlassGroup<Content: View>: View {
    init(spacing: CGFloat = 12, @ViewBuilder content: () -> Content)
    // iOS 26: GlassEffectContainer(spacing:content:); fallback: content()
}
```

iOS 26 API reference (exact, from the SDK):
`View.glassEffect(_ glass: Glass = .regular, in shape: some Shape)`;
`Glass` supports `.regular`, `.regular.tint(_ color: Color)`,
`.regular.interactive()`; `GlassEffectContainer(spacing: CGFloat?, content:)`.
Wrap ALL uses in `if #available(iOS 26.0, *)`.

`Components.swift`:
```swift
struct LineChip: View {        // filter pill for one line
    let line: CTALine
    let isSelected: Bool
    let action: () -> Void
}
struct AllLinesChip: View {
    let isSelected: Bool
    let action: () -> Void
}
struct StatusPill: View {      // "LIVE · 12:04:31" bottom-center pill
    let lastUpdated: Date?
    let connectionLost: Bool
}
struct ArrivalPill: View {     // bordered "Scheduled 4 min" / tinted "Predicted ~6 min"
    enum Kind { case scheduled, predicted }
    let kind: Kind
    let label: String          // "Scheduled" / "Predicted"
    let value: String          // "4 min" / "Now" / "~6 min"
    let tint: Color?           // line color for predicted, nil for scheduled
}
```

Chips: capsule, line-color fill at ~0.85 opacity + white text when selected;
liquid glass + line-colored text when not. 44 pt min height. AllLinesChip says
"ALL". StatusPill: green pulsing dot (scale/opacity animation) + monospaced
digits time, red dot + "OFFLINE" when connectionLost.

### Features/Map (agent B)

```swift
struct TrainMapView: View {
    @Bindable var model: AppModel
    // SwiftUI Map(position:) with .standard(elevation:emphasis:) dark styling:
    //   .mapStyle(.standard(pointsOfInterest: .excludingAll))
    //   .preferredColorScheme(.dark) is set at root; map shows default dark.
    // Content:
    //   MapPolyline(coordinates:) .stroke(line.color, lineWidth: 3) per RoutePolyline (selected lines only)
    //   Station dots: Annotation of 10pt circle, white 0.9 fill, 1.5pt line-color stroke when single line
    //     (gray stroke when multi-line), tap → model.select(station:)
    //   Trains: Annotation with TrainMarker (below), rotated by heading
    // Initial camera: Chicago Loop, center (41.8781, -87.6298), ~0.35° span.
}

struct TrainMarker: View {     // MapContent.swift
    let train: Train
    // 22pt circle filled with train.line.color, white chevron.up rotated to heading,
    // white 2pt stroke, shadow; small red ring pulse when isDelayed.
}
```

Use `MapReader`/plain `Annotation` — DO NOT use deprecated MapKit UIViewRepresentable.
Everything here is iOS 17-compatible MapContentBuilder API.
Station tap: `.onTapGesture` on the annotation content view.

### Features/Station (agent C)

```swift
struct StationSheet: View {
    @Bindable var model: AppModel
    // Presented from RootView via .sheet(item:) — this view is the sheet CONTENT.
    // Header: station name (title2 bold), line chips (small colored capsules), close X.
    // Body: ForEach(model.arrivals?.directions) → DirectionSection.
    // States: loading spinner, error "Couldn't load arrivals" + Retry button,
    //         empty "No upcoming arrivals".
    // Refresh button calls model.refreshArrivals().
}

struct DirectionSection: View {   // ArrivalRow.swift
    let group: DirectionGroup
    // "Red · toward 95th/Dan Ryan" header with line-colored route chip, then
    // up to 3 ArrivalRow.
}

struct ArrivalRow: View {
    let arrival: Arrival
    let line: CTALine?
    // "→ destination" + ArrivalPill(scheduled) + ArrivalPill(predicted, tint: line color)
    // when arrival.predictedMinutes != nil. "⚠" on isDelayed. delay_status caption
    // under pills in secondaryText.
}
```

### App (agent E)

```swift
@main
struct ChicagoLMapApp: App {
    // WindowGroup { RootView() } .preferredColorScheme(.dark)
}

struct RootView: View {
    @State private var model = AppModel()
    // ZStack: TrainMapView full-bleed;
    // top: title bar — "Chicago 'L' Live" + train count, liquid glass capsule, safe-area aware;
    // bottom: GlassGroup horizontal ScrollView of AllLinesChip + 8 LineChips, and StatusPill above it;
    // .sheet(item: $model.selectedStation) { _ in StationSheet(model: model)
    //     .presentationDetents([.fraction(0.45), .large])
    //     .presentationDragIndicator(.visible)
    //     .presentationBackground(.thinMaterial) }
    // .task { await model.start() }
    // Station? must be Identifiable (it is — id: Int).
}
```

## Style rules

- Every file compiles under Swift 5 mode with strict-concurrency=minimal.
- `import SwiftUI`, `import MapKit`, `import CoreLocation` as needed; nothing else.
- No force-unwraps except statically-safe literals (e.g. `URL(string:)!` of a constant).
- No TODOs, no placeholder bodies — production-complete code.
- Animations: subtle spring on chip selection, `.animation(.default, value:)` on train positions so markers glide between polls.

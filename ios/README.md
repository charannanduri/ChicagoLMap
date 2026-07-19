# Chicago L Map — iOS App

Native SwiftUI app for the live Chicago 'L' map with ML delay predictions,
talking to the same backend as the website (`https://chicagolmap.onrender.com`).

- **iOS 17+**, built with Xcode 26. On iOS 26 the UI uses the real **Liquid
  Glass** system materials (`glassEffect`, `GlassEffectContainer`); older
  versions get a matching ultra-thin-material fallback.
- No third-party dependencies. The Xcode project is generated from
  `project.yml` by [XcodeGen](https://github.com/yonaskolb/XcodeGen) — no
  `.xcodeproj` is checked in.

## No Xcode? No problem

Everything builds on GitHub Actions (`.github/workflows/ios-build.yml`):

### 1. Try it in the browser (zero Apple account needed)
Every push to `main` that touches `ios/` runs the **build-simulator** job and
uploads a `ChicagoLMap-Simulator` artifact (a zipped simulator `.app`).

1. Actions → **iOS App** → latest run → download `ChicagoLMap-Simulator`.
2. Go to [appetize.io](https://appetize.io) (free tier), upload the zip,
   pick any iPhone, and use the app right in your browser.

### 2. TestFlight on your actual iPhone
Requires an [Apple Developer Program](https://developer.apple.com/programs/)
membership ($99/yr). One-time setup:

1. **App Store Connect → Users and Access → Integrations → App Store Connect
   API** → generate an API key with the **App Manager** role. Note the
   **Key ID** and **Issuer ID**, download the `.p8` file.
2. **App Store Connect → Apps → “+”** → New App: platform iOS, bundle ID
   `com.charannanduri.chicagolmap` (register the bundle ID at
   developer.apple.com → Identifiers if prompted), any SKU.
3. In this GitHub repo → Settings → Secrets and variables → Actions, add:
   | Secret | Value |
   |---|---|
   | `ASC_KEY_ID` | the API Key ID |
   | `ASC_ISSUER_ID` | the Issuer ID |
   | `ASC_KEY_P8` | full contents of the downloaded `.p8` file |
   | `APPLE_TEAM_ID` | your 10-char Team ID (developer.apple.com → Membership) |
4. Actions → **iOS App** → **Run workflow** → check **“Archive and upload to
   TestFlight”** → Run. Cloud signing is automatic (`-allowProvisioningUpdates`
   with the API key) — no certificates to export.
5. When processing finishes (~10 min), open **TestFlight** on your iPhone,
   add yourself as an internal tester in App Store Connect, and install.

## Layout

```
ios/
  project.yml          XcodeGen project spec (bundle id, targets, Info.plist keys)
  SPEC.md              design/API contract the app was built against
  ChicagoLMap/
    App/               app entry + root composition
    Core/              models, API client, observable app model (polling)
    DesignSystem/      Liquid Glass abstraction, theme, shared components
    Features/Map/      MapKit live map (trains, stations, route polylines)
    Features/Station/  station sheet with CTA ETAs + ML "Predicted" pills
    Resources/         asset catalog (app icon, accent color)
```

## Local development (if you ever get a Mac with space)

```bash
brew install xcodegen
cd ios && xcodegen generate && open ChicagoLMap.xcodeproj
```

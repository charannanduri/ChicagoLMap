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

### 2. Sideload onto your iPhone (no Apple Developer Program)
Every build also uploads **`ChicagoLMap-unsigned-ipa`** — a real device build,
packaged as an `.ipa`.

It is **unsigned**, so it cannot be installed by itself: iOS only runs signed
code. Sideloading tools sign it with your own free Apple ID as they install it:

| Tool | Needs a computer? | Notes |
|---|---|---|
| [AltStore](https://altstore.io) | Yes, on the same Wi-Fi | Refreshes apps automatically while AltServer runs |
| [SideStore](https://sidestore.io) | Only for first-time pairing | Refreshes on-device afterwards |
| [Sideloadly](https://sideloadly.io) | Yes | One-off installs |

Free-Apple-ID limits worth knowing before you start: the app **expires after 7
days** and must be re-signed, you can have at most 3 sideloaded apps at once,
and the device must be registered to that Apple ID. A paid Developer account
raises the signing validity to a year — at which point TestFlight (below) is
simply the better route.

### 3. TestFlight on your actual iPhone
Requires an [Apple Developer Program](https://developer.apple.com/programs/)
membership ($99/yr). One-time setup:

1. **App Store Connect → Users and Access → Integrations → App Store Connect
   API** → generate an API key with the **Admin** role. Note the **Key ID** and
   **Issuer ID**, download the `.p8` file.

   > The role must be **Admin**, not App Manager. Cloud signing has to create a
   > cloud-managed *distribution* certificate, and only Admins and the Account
   > Holder may do that. An App Manager key archives fine and then fails at
   > export with `Cloud signing permission error` followed by
   > `No profiles for '<bundle id>' were found`.
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

## App Store / TestFlight readiness

Handled in this repo:

| Requirement | Status |
|---|---|
| **Privacy manifest** (`PrivacyInfo.xcprivacy`) | Declares UserDefaults (`CA92.1`) — the only required-reason API used. CI fails the build if it isn't in the bundle. Without it, uploads raise `ITMS-91053` |
| **Export compliance** | `ITSAppUsesNonExemptEncryption = NO` (HTTPS only). Stops builds sitting in "Missing Compliance" |
| **Location purpose string** | `NSLocationWhenInUseUsageDescription` explains the nearest-station feature |
| **App icon** | 1024×1024, **no alpha channel** (Apple rejects icons with transparency) |
| **App Transport Security** | Every request is HTTPS; no ATS exceptions needed |
| **Launch screen** | Generated (`UILaunchScreen_Generation`), required for full-screen layout |
| **Version / build number** | `MARKETING_VERSION` 1.0, build number from the CI run number so it always increases |
| **Third-party SDKs** | None — no bundled SDK privacy manifests to chase |
| **Data attribution** | Credits the CTA and states there is no affiliation |

You still have to do, in App Store Connect:

1. **Register the bundle ID** `com.charannanduri.chicagolmap` (or let the archive step create it — it runs with `-allowProvisioningUpdates`).
2. **Create the app record.** The upload fails without one; the bundle ID alone is not enough.
3. **Add yourself as an internal tester.** Internal testers skip Beta App Review entirely, so builds are installable as soon as processing finishes.

Worth knowing before a public App Store release (none of this blocks TestFlight):

- **External testers** — more than internal ones, or anyone outside your team, requires Beta App Review, plus a description and contact details.
- **Naming and branding** — reviewers are wary of apps that could read as official transit apps. The in-app "not affiliated with or endorsed by the CTA" line helps; keep the App Store name, subtitle and screenshots clear of CTA logos and livery.
- **CTA API terms** — the Train Tracker licence governs redistribution and attribution. Worth reading before charging for anything or scaling distribution.
- **Guideline 5.1.1** — location is requested only when you open "Riding a train?", and the app works without it. That is the pattern reviewers expect.

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

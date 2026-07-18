import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CTA Delay Predictor",
  description: "Red and Blue Line delay predictions for Chicago CTA trains",
};

export const viewport: Viewport = {
  // device-width + initialScale keep text readable without zoom.
  // We intentionally do NOT set maximumScale/userScalable so pinch-zoom
  // stays available for accessibility.
  width: "device-width",
  initialScale: 1,
  // Required for env(safe-area-inset-*) to resolve on iOS Safari so fixed/
  // sticky chrome isn't hidden behind the notch, home indicator, or the
  // dynamic address bar (which can sit at the top OR bottom of the screen).
  viewportFit: "cover",
  themeColor: "#030712",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-950 text-gray-100 font-sans antialiased">
        <header className="sticky top-0 z-20 flex items-center gap-4 border-b border-gray-800 bg-gray-950/90 px-4 py-3 backdrop-blur pt-[calc(0.75rem+env(safe-area-inset-top))] pl-[calc(1rem+env(safe-area-inset-left))] pr-[calc(1rem+env(safe-area-inset-right))]">
          <span className="text-lg font-bold tracking-tight">CTA Delay Predictor</span>
          <span className="text-xs text-gray-400 hidden sm:inline">
            Red &amp; Blue Line statistical delay estimates
          </span>
        </header>
        <main className="max-w-4xl mx-auto px-4 py-6 pb-[calc(1.5rem+env(safe-area-inset-bottom))] pl-[calc(1rem+env(safe-area-inset-left))] pr-[calc(1rem+env(safe-area-inset-right))]">
          {children}
        </main>
      </body>
    </html>
  );
}

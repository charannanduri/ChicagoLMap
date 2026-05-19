import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CTA Delay Predictor",
  description: "Red and Blue Line delay predictions for Chicago CTA trains",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-950 text-gray-100 min-h-screen font-sans antialiased">
        <header className="border-b border-gray-800 px-4 py-3 flex items-center gap-4">
          <span className="text-lg font-bold tracking-tight">CTA Delay Predictor</span>
          <span className="text-xs text-gray-400 hidden sm:inline">
            Red &amp; Blue Line statistical delay estimates
          </span>
        </header>
        <main className="max-w-4xl mx-auto px-4 py-6">{children}</main>
      </body>
    </html>
  );
}

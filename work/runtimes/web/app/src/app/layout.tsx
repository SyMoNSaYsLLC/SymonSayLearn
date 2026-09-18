// SPDX-License-Identifier: FSL-1.1-ALv2
// Copyright 2026 SymonSaysLLC
// SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Nav } from "@/components/Nav";

/* The application shell.
 *
 * A fixed sidebar and a content column, because every surface here is a peer:
 * Chat, Code and Cowork are three views of one estate, not a hierarchy, and a
 * sidebar says that where nested navigation would not.
 *
 * The three surfaces are listed first and together, mirroring the three model
 * cards the gateway serves. The operator views follow, separated, because
 * looking at the rack is a different activity from using it.
 */

export const metadata: Metadata = {
  title: "SyMoNeuRaL",
  description: "This estate's own runtimes, on this machine.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Both schemes are authored, so the browser should render form controls and
  // scrollbars to match rather than forcing one.
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f7f6f4" },
    { media: "(prefers-color-scheme: dark)", color: "#1a1917" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <aside className="sidebar">
            <div className="brand">
              {/* Placeholder mark. The real one is symoneural-mark-teal.svg; it is
                  not used yet because every asset in ~/Desktop/brand is dated
                  2026-08-16 and rules section 3.2 bars August material. */}
              <div className="brand-mark" aria-hidden="true" />
              <span className="brand-name">SyMoNeuRaL</span>
            </div>
            <Nav />
            <div style={{ marginTop: "auto" }}>
              <p className="faint" style={{ fontSize: "var(--text-xs)", margin: 0 }}>
                Local only. Nothing here leaves this machine.
              </p>
            </div>
          </aside>
          <main className="main">{children}</main>
        </div>
      </body>
    </html>
  );
}

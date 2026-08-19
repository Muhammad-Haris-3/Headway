import type { Metadata } from "next";
import { IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

const sans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400","500","600","700"], variable: "--font-sans", display: "swap" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400","500","600"], variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  title: "Headway — keeping score on published arrival predictions",
  description:
    "Transit agencies publish millions of arrival predictions and their own error bars. Nobody keeps score. Headway records them before the outcome exists.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body>
        <div className="shell">
          <header className="site">
            <div className="in">
              <b>Headway</b>
              <i>keeping score on published arrival predictions</i>
            </div>
          </header>
          <main>{children}</main>
          <footer className="site">
            <div className="in">
              <span style={{ maxWidth: "60ch" }}>
                Everything here describes the <strong>MBTA</strong> and generalises to no other
                operator. It measures published predictions; it is not advice about any journey.
                Data from the public MBTA v3 API.{" "}
                <a href="https://github.com/Muhammad-Haris-3/Headway">Source, method and pre-registration</a>
              </span>
              <span className="mono" style={{ fontSize: ".58rem", letterSpacing: ".18em", textTransform: "uppercase" }}>
                Muhammad Haris
              </span>
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}

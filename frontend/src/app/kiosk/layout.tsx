import type { Metadata, Viewport } from "next";

export const metadata: Metadata = { title: "Visitor kiosk" };
export const viewport: Viewport = { width: "device-width", initialScale: 1, maximumScale: 1, userScalable: false, themeColor: "#070f24" };

export default function KioskLayout({ children }: { children: React.ReactNode }) {
  return children;
}

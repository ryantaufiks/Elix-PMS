import type { Metadata, Viewport } from "next";

import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: { default: "Elix PMS", template: "%s · Elix PMS" },
  description: "Visitor management and access control dashboard",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#0f766e" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-SG">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

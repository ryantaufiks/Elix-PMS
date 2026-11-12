import type { Metadata } from "next";

import { Landing } from "@/components/landing/Landing";

export const metadata: Metadata = {
  title: { absolute: "Elix · Visitor management and access control for Singapore condominiums" },
  description: "Lobby kiosk, video intercom, QR invitations, licence-plate entry and a resident app, with PDPA built in. Made for Singapore condominiums.",
  robots: { index: true, follow: true },
};

export default function HomePage() {
  return <Landing />;
}

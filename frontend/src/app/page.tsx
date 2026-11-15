import type { Metadata } from "next";

import { Landing } from "@/components/landing/Landing";

export const metadata: Metadata = {
  title: { absolute: "Elix · Visitor management and access control for Singapore condominiums" },
  description: "One platform for everyone who comes through your gate: visitors, residents, contractors and vendors. Lobby kiosk, video intercom, renovation permits and licence-plate entry, with PDPA built in. Built for Singapore condominiums.",
  robots: { index: true, follow: true },
};

export default function HomePage() {
  return <Landing />;
}

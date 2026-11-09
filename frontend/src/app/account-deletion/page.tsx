import type { Metadata } from "next";

import { LegalPage } from "@/components/LegalPage";
import { PRIVACY_EMAIL } from "@/lib/legal";

export const metadata: Metadata = { title: "Delete your account", robots: { index: true, follow: true } };

export default function AccountDeletionPage() {
  const mail = `mailto:${PRIVACY_EMAIL}?subject=${encodeURIComponent("Elix account deletion request")}`;
  return (
    <LegalPage title="Delete your Elix account" updated="9 November 2026">
      <p>
        Elix accounts are created by your condominium&apos;s management for residents of the estate. You can ask for your
        account and its data to be deleted at any time, even while you still live there.
      </p>

      <h2>How to ask</h2>
      <ul>
        <li>Tell your estate&apos;s management office, or</li>
        <li>
          Email <a href={mail}>{PRIVACY_EMAIL}</a> from the email address on your account, with your name, estate and
          unit number.
        </li>
      </ul>
      <p>We confirm the request with your management and delete the account within 30 days.</p>

      <h2>What is deleted</h2>
      <ul>
        <li>Your account, name, contact details and sign-in.</li>
        <li>Vehicles you registered and invitations you created.</li>
        <li>Your facility bookings, feedback and notification tokens.</li>
        <li>Documents kept for you, unless the management must keep them for the unit (for example a tenancy record).</li>
      </ul>

      <h2>What may be kept</h2>
      <p>
        Gate and visitor logs that mention your unit are kept as estate security records until the estate&apos;s retention
        period ends, and payment records are kept as long as the law requires. Backups containing your data are
        deleted automatically within 14 days.
      </p>
    </LegalPage>
  );
}

import type { Metadata } from "next";

import { SUPPORTED_BY } from "@/components/Credit";
import { LegalPage } from "@/components/LegalPage";
import { PRIVACY_EMAIL } from "@/lib/legal";

export const metadata: Metadata = { title: "Privacy policy", robots: { index: true, follow: true } };

export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy policy" updated="11 October 2026">
      <p>
        Elix is a visitor management and access control service for condominiums in Singapore. It is made up of the
        Elix resident app, the lobby kiosk and the management dashboard. The service is provided by {SUPPORTED_BY} on
        behalf of each condominium&apos;s management corporation or managing agent (&ldquo;the management&rdquo;),
        which decides how the service is used at its estate. This policy explains what data Elix handles and why, in
        line with Singapore&apos;s Personal Data Protection Act (PDPA).
      </p>

      <h2>Residents (the Elix app)</h2>
      <ul>
        <li><strong>Account details</strong> from the management: your name, username, unit, mobile number and email.</li>
        <li><strong>Visitor invitations</strong> you create: the visitor&apos;s name, mobile number, vehicle plate, purpose and validity.</li>
        <li><strong>Vehicles</strong> you register: plate number, make, model and colour, so the barrier can open for you.</li>
        <li><strong>Documents</strong> the management keeps for your unit, such as proof of ownership or a tenancy agreement.</li>
        <li><strong>Facility bookings and payments.</strong> Payments are handled by our payment provider (HitPay); Elix never sees your card details.</li>
        <li><strong>Feedback</strong> you send to the management.</li>
        <li><strong>Camera and microphone</strong>, only during a video intercom call you answer. Calls are not recorded.</li>
        <li><strong>Device data</strong>: a notification token so calls can reach you, and basic technical logs (time, app version) to keep the service running.</li>
      </ul>

      <h2>Visitors</h2>
      <p>
        At the kiosk or the gate, visitors give their name, purpose and, where the estate requires them, a mobile number,
        the last 4 characters of their NRIC/FIN, a photo and a vehicle plate (read by the gate camera). The resident being
        visited sees these details so they can let the visitor in. Face matching, where an estate turns it on, is used
        only with the visitor&apos;s consent. The kiosk&apos;s voice assistant processes speech to answer the visitor;
        conversations are not stored.
      </p>

      <h2>How we use the data</h2>
      <ul>
        <li>To let residents and the management decide who enters the estate, and to open gates and barriers.</li>
        <li>To connect visitors to residents by video intercom.</li>
        <li>To run facility bookings, documents and feedback for the estate.</li>
        <li>To keep the estate secure, investigate incidents and keep the service working.</li>
      </ul>
      <p>We do not sell personal data and do not use it for advertising.</p>

      <h2>Who sees it</h2>
      <ul>
        <li>The management and security staff of your estate.</li>
        <li>Residents, for their own unit&apos;s visitors, invitations and activity.</li>
        <li>
          Service providers we use to run Elix, under contract and only for that purpose: cloud hosting, video calling,
          push notifications (Google Firebase), payments (HitPay) and the kiosk voice assistant (OpenAI).
        </li>
        <li>Authorities, when the law requires it.</li>
      </ul>

      <h2>How long we keep it</h2>
      <p>
        Visitor personal data is deleted automatically after the retention period your estate sets. Resident data is kept
        while you live at the estate and have an account, then deleted when the management removes the account or you
        ask us to (see <a href="/account-deletion/">Delete your account</a>). Backups are deleted automatically after
        14 days.
      </p>

      <h2>Security</h2>
      <p>
        Data is sent over encrypted connections (HTTPS), photos and documents are only served to signed-in users with
        access to them, and access to the dashboard depends on each staff member&apos;s role.
      </p>

      <h2>Your choices and rights</h2>
      <p>
        You can ask to see or correct your personal data, or withdraw consent, through your estate&apos;s management
        office or by writing to us. You can turn off camera, microphone and notification permissions in your phone&apos;s
        settings at any time; video calls will not work without them. Elix is not intended for children under 13.
      </p>

      <h2>Contact</h2>
      <p>
        Questions about this policy or your data: <a href={`mailto:${PRIVACY_EMAIL}`}>{PRIVACY_EMAIL}</a>, or your
        estate&apos;s management office. We may update this policy and will change the date above when we do.
      </p>
    </LegalPage>
  );
}

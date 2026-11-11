import type { Metadata } from "next";

import { SUPPORTED_BY } from "@/components/Credit";
import { LegalPage } from "@/components/LegalPage";
import { PRIVACY_EMAIL } from "@/lib/legal";

export const metadata: Metadata = { title: "Cybersecurity policy", robots: { index: true, follow: true } };

export default function SecurityPage() {
  return (
    <LegalPage title="Cybersecurity policy" updated="11 November 2026">
      <p>
        This policy sets out how {SUPPORTED_BY} protects the Elix service (the resident app, the lobby kiosk and the
        management dashboard) and the data the estates we serve entrust to us. It applies to everyone who builds,
        runs or supports Elix. How personal data is collected and used is covered by our{" "}
        <a href="/privacy/">Privacy policy</a>.
      </p>

      <h2>Hosting and network</h2>
      <ul>
        <li>Elix runs on cloud servers. The application is published through Cloudflare; the servers accept no inbound web connections directly.</li>
        <li>All traffic between the apps, kiosks, dashboard and servers is encrypted (HTTPS); plain HTTP is redirected to HTTPS.</li>
        <li>Server administration uses SSH keys. Password sign-in is allowed only over a private network, and repeated failed attempts are blocked automatically.</li>
        <li>A host security agent monitors the production servers.</li>
      </ul>

      <h2>Access control</h2>
      <ul>
        <li>Access is role-based: platform administrator, site admin, staff and security, and residents. Each account sees only its own estate.</li>
        <li>Passwords must meet length and strength rules, are stored hashed and are never visible to anyone. Repeated sign-in attempts are rate limited.</li>
        <li>Accounts are personal and must not be shared. When staff leave, their account is deactivated straight away.</li>
        <li>Only people who need it to run the service have administrator access to the platform or the servers.</li>
      </ul>

      <h2>Protecting data</h2>
      <ul>
        <li>Credentials for gates, cameras and payment accounts are encrypted at rest.</li>
        <li>Photos and documents are served only to signed-in users with access to them.</li>
        <li>Visitor personal data is deleted automatically after the retention period each estate sets.</li>
        <li>Data exports never contain passwords, secrets or face data.</li>
      </ul>

      <h2>Updates</h2>
      <p>
        Operating system security updates are installed automatically every day. Application components are kept on
        supported versions and updated with each release. Systems that are no longer supported by their maker are not
        used.
      </p>

      <h2>Backups</h2>
      <p>
        The whole platform (database and uploaded files) is backed up automatically every day and each backup is kept
        for 14 days. A backup is also taken before every system update. Backups can be downloaded by the platform
        administrator to keep a copy away from the servers.
      </p>

      <h2>Incidents</h2>
      <p>
        If we suspect a security incident, we act at once to contain it, find the cause and restore the service. We
        inform the affected estates&apos; management without undue delay, and notify the Personal Data Protection
        Commission and affected individuals where the PDPA requires it. Each incident is reviewed afterwards so it does
        not happen again.
      </p>

      <h2>Your part</h2>
      <ul>
        <li>Keep your password to yourself and choose one you do not use elsewhere.</li>
        <li>Sign out of shared computers, and lock kiosks and guardhouse PCs when unattended.</li>
        <li>Site admins: remove accounts of staff and residents who leave, and give each person only the role they need.</li>
        <li>Be wary of emails or messages asking for your password. Elix will never ask for it.</li>
      </ul>

      <h2>Reporting a security issue</h2>
      <p>
        If you believe you have found a vulnerability or that an account has been misused, write to{" "}
        <a href={`mailto:${PRIVACY_EMAIL}`}>{PRIVACY_EMAIL}</a>. Please do not share the details publicly until we have
        fixed it. We review this policy at least once a year and will change the date above when we update it.
      </p>
    </LegalPage>
  );
}

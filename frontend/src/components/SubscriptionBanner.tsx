"use client";

import { useSession } from "@/lib/session";
import { formatDate } from "@/lib/format";
import { Icon } from "./icons";
import { cx } from "./ui";

const DAY = 86_400_000;

/** Trial ending soon, grace period or suspension: shown to the site's admins (and the platform admin). */
export function SubscriptionBanner() {
  const { condo, isAdmin, me } = useSession();
  if (!isAdmin && !me.is_superuser) return null;
  const status = condo.subscription_status;
  const ends = condo.subscription_ends_on;
  const days = ends ? Math.ceil((new Date(`${ends}T23:59:59+08:00`).getTime() - Date.now()) / DAY) : null;

  let tone = "";
  let text = "";
  if (status === "trial" && days !== null && days <= 7) {
    tone = "border-primary-500/30 bg-primary-500/10 text-primary-800 dark:text-primary-200";
    text = days <= 0 ? "The trial ends today." : `The trial ends in ${days} day${days === 1 ? "" : "s"} (${formatDate(ends)}). Contact Elix to subscribe.`;
  } else if (status === "grace") {
    tone = "border-amber-500/40 bg-amber-500/10 text-amber-900 dark:text-amber-200";
    text = `Subscription overdue. Everything keeps working until ${formatDate(ends)}; after that premium features stop and setup is locked. Contact Elix to renew.`;
  } else if (status === "suspended") {
    tone = "border-rose-500/40 bg-rose-500/10 text-rose-800 dark:text-rose-200";
    text = "Subscription suspended. Gates, plate recognition and the basic kiosk keep working; premium features are off and setup is locked. Contact Elix to renew.";
  }
  if (!text) return null;
  return (
    <div className="mx-auto max-w-7xl px-4 pt-4 sm:px-8">
      <div role="status" className={cx("flex items-start gap-3 rounded-xl border px-4 py-3 text-sm", tone)}>
        <Icon name={status === "trial" ? "bell" : "lock"} className="mt-0.5 h-4 w-4 shrink-0" />
        <span>{text}</span>
      </div>
    </div>
  );
}

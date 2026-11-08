import { cx } from "./ui";

export const SUPPORTED_BY = "Smart City Technologies Pte Ltd";
export const COPYRIGHT_YEAR = 2026;

/** The "Supported by … / © year" footer shown on every page. `tone="dark"` is for the navy brand panels. */
export function Credit({ tone = "light", align = "center", className }: { tone?: "light" | "dark"; align?: "center" | "left"; className?: string }) {
  return (
    <footer className={cx("text-xs leading-relaxed", align === "left" ? "text-left" : "text-center", tone === "dark" ? "text-slate-400" : "text-muted", className)}>
      <div>Supported by <span className={cx("font-medium", tone === "dark" ? "text-slate-300" : "text-body")}>{SUPPORTED_BY}</span></div>
      <div>© {COPYRIGHT_YEAR} ELIX. All rights reserved.</div>
    </footer>
  );
}

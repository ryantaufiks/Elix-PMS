"use client";

import Link from "next/link";

import { Credit } from "@/components/Credit";
import { Icon, type IconName } from "@/components/icons";
import { PRIVACY_EMAIL } from "@/lib/legal";

import { DEMO_MAIL, LandingNav } from "./LandingNav";
import { StoreBadges } from "./StoreBadges";
import { Workflow } from "./Workflow";

const quote = (plan: string) => "mailto:services@smartcitytechnologies.com.sg?subject=" + encodeURIComponent(`Elix ${plan} plan: request a quote`)
  + "&body=" + encodeURIComponent(`Hello Elix team,\n\nPlease send a quote for the ${plan} plan.\n\nCondominium:\nNumber of units:\nNumber of gates:\nContact person and phone:\n`);

const FEATURES: { icon: IconName; title: string; text: string }[] = [
  { icon: "tablet", title: "Lobby kiosk", text: "Visitors call a unit, register as a walk-in or show their invitation on any tablet, in English, 中文, Melayu or தமிழ். Big buttons and a number pad." },
  { icon: "video", title: "Video intercom", text: "The resident's phone rings with the visitor's photo. Talk face to face, then swipe to open the gate. Visitors who need help call the guardhouse instead." },
  { icon: "users", title: "Guardhouse dashboard", text: "Who is on site, since when and who has overstayed, with alerts per visitor type. Kiosk calls pop up and ring on any page." },
  { icon: "qr", title: "QR invitations", text: "Residents invite guests in seconds. Guests get a pass by link, with validity, entries and plate, no app needed." },
  { icon: "car", title: "Licence-plate entry", text: "Cameras at the barrier let residents and invited cars straight in, and log every read with a snapshot." },
  { icon: "ticket", title: "Vehicle passes", text: "Residents' cars, temporary passes and season parking, each with start and end dates. Residents buy and renew season parking in the app." },
  { icon: "smartphone", title: "Resident app", text: "Calls, gate opening, invitations, facility bookings, documents and feedback in one Android app." },
  { icon: "calendar", title: "Facility booking", text: "BBQ pits, function rooms and courts with slots, rules and PayNow. Residents check in at the kiosk with a QR; no-shows are flagged." },
  { icon: "printer", title: "Walk-in passes", text: "A printed slip with a pass number for security, and self check-out with its QR or PIN when visitors leave." },
  { icon: "report", title: "Reports and insights", text: "Visitor, access, vehicle, intercom and invitation reports for one or many sites, busiest hours for planning shifts, and PDF, Excel or CSV." },
  { icon: "sparkle", title: "AI concierge", text: "Elixa, a voice assistant at the kiosk: directions, facilities, help registering, and a call to the guardhouse when a person is needed." },
  { icon: "eye", title: "Accessible", text: "Designed to WCAG 2.1 AA: high contrast, a larger text option for staff, and a \u201cmore time?\u201d prompt at the kiosk." },
];

const PLANS = [
  { name: "Basic", tagline: "Kiosk and management dashboard", features: ["Lobby kiosk in four languages: walk-ins and QR check-in", "Visitor dashboard with overstay alerts", "Visitor list, access log and gate control", "Vehicle passes with start and end dates", "Staff and guardhouse accounts", "On-screen reports"] },
  { name: "Standard", tagline: "Adds the residents", highlight: true, features: ["Everything in Basic", "Resident app (Android)", "Video intercom, also to the guardhouse", "Facility booking, kiosk check-in and no-shows", "Season parking paid in the app", "Report insights and export: PDF, Excel and CSV"] },
  { name: "Premium", tagline: "The full estate experience", features: ["Everything in Standard", "Licence-plate recognition", "Face check at the kiosk", "AI voice concierge that can call the guardhouse"] },
];

const PDPA = [
  ["Consent first", "The kiosk shows your estate's privacy notice and asks for consent before taking any details or photo."],
  ["Collect less", "Only the last 4 characters of NRIC/FIN, never the full number. Mobile and ID are optional."],
  ["Deleted on schedule", "Visitor names, contacts, photos and plates are erased automatically after the period your estate sets (90 days by default)."],
  ["Faces only with permission", "Face check-out is off unless the estate turns it on; only a face template is kept, and deleted at check-out."],
  ["Residents in control", "Residents can ask for their account and data to be deleted; the app links straight to the request."],
  ["Clear roles", "Officers handle visitors and gates; residents' documents stay with the management office. Lobby screens never show who booked what."],
];

const TECH: { icon: IconName; title: string; text: string }[] = [
  { icon: "cloud", title: "Cloud, nothing to install", text: "The dashboard runs in the browser; the kiosk runs on any tablet with a camera." },
  { icon: "zap", title: "Live", text: "Calls, gate events and visitors appear the moment they happen, on every screen." },
  { icon: "gate", title: "Works with your gates", text: "Smart relays on existing gate motors and barriers, controlled over the network or the cloud." },
  { icon: "camera", title: "Plate cameras", text: "Licence-plate cameras at the barrier send each read straight to Elix." },
  { icon: "building", title: "Many sites, one account", text: "Managing agents with several estates switch between them in one account." },
  { icon: "globe", title: "Made for Singapore", text: "SGT everywhere, Singapore plates and postal codes, PayNow, PDPA built in, and a kiosk in the four official languages." },
];

const SECURITY = [
  "HTTPS everywhere; nothing is served without encryption",
  "Every account sees only its own estate, by role",
  "Device and payment credentials encrypted at rest",
  "Password rules and sign-in rate limiting",
  "Daily backups of the whole platform, kept 14 days",
  "Automatic security updates and host monitoring",
];

function Section({ id, eyebrow, title, intro, children, dark }: {
  id: string; eyebrow: string; title: string; intro?: string; children: React.ReactNode; dark?: boolean;
}) {
  return (
    <section id={id} className={dark ? "brand-panel scroll-mt-16 text-white" : "scroll-mt-16 bg-canvas"}>
      <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-24">
        <div className="mx-auto max-w-2xl text-center">
          <div className={dark ? "text-sm font-semibold uppercase tracking-widest text-primary-300" : "text-sm font-semibold uppercase tracking-widest text-primary-500 dark:text-primary-300"}>{eyebrow}</div>
          <h2 className={dark ? "mt-3 text-3xl font-semibold tracking-tight sm:text-4xl" : "mt-3 text-3xl font-semibold tracking-tight text-ink sm:text-4xl"}>{title}</h2>
          {intro && <p className={dark ? "mt-4 text-lg text-slate-300" : "mt-4 text-lg text-muted"}>{intro}</p>}
        </div>
        <div className="mt-12">{children}</div>
      </div>
    </section>
  );
}

export function Landing() {
  return (
    <div id="top" className="min-h-dvh bg-canvas">
      <LandingNav />

      {/* Hero */}
      <section className="brand-panel relative overflow-hidden text-white">
        <div className="pointer-events-none absolute inset-0 opacity-[0.07] [background-image:linear-gradient(rgb(255_255_255/0.6)_1px,transparent_1px),linear-gradient(90deg,rgb(255_255_255/0.6)_1px,transparent_1px)] [background-size:48px_48px]" />
        <div className="relative mx-auto max-w-6xl px-4 pb-24 pt-36 text-center sm:px-6 sm:pt-44">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/brand/elix-logo.png" alt="Elix" className="mx-auto h-16 w-auto drop-shadow-[0_0_30px_rgba(47,111,255,0.55)] sm:h-24" />
          <h1 className="mx-auto mt-8 max-w-3xl text-4xl font-semibold tracking-tight sm:text-6xl">Engage Link Identified Experience</h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-slate-300 sm:text-xl">
            Visitor management and access control for Singapore condominiums: a lobby kiosk, a resident app and one dashboard for the management office.
          </p>
          <div className="mt-10 flex flex-wrap justify-center gap-3">
            <a href={DEMO_MAIL} className="rounded-xl bg-primary-500 px-6 py-3.5 text-base font-semibold text-white shadow-primary transition hover:bg-primary-600">Request a demo</a>
            <a href="#how" className="rounded-xl border border-white/20 bg-white/5 px-6 py-3.5 text-base font-semibold text-white transition hover:bg-white/10">See how it works</a>
          </div>
          <div className="mt-14 flex flex-wrap justify-center gap-x-8 gap-y-3 text-sm text-slate-300">
            {["PDPA built in", "Works with existing gates", "Live on every screen", "Four languages", "Designed to WCAG 2.1 AA"].map((t) => (
              <span key={t} className="flex items-center gap-2">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary-500/25 text-primary-300"><Icon name="check" className="h-3 w-3" /></span>{t}
              </span>
            ))}
          </div>
        </div>
      </section>

      <Section id="features" eyebrow="Features" title="Everything between the gate and the front door"
        intro="One platform for the guardhouse, the management office and every resident.">
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="rounded-2xl border border-line bg-surface p-6 shadow-card transition hover:-translate-y-0.5 hover:border-primary-400/50">
              <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary-500/10 text-primary-500 dark:text-primary-300"><Icon name={f.icon} className="h-6 w-6" /></span>
              <h3 className="mt-4 text-lg font-semibold text-ink">{f.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted">{f.text}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* The resident app, and where it will be available. */}
      <section className="bg-canvas">
        <div className="mx-auto max-w-6xl px-4 pb-20 sm:px-6">
          <div className="brand-panel relative overflow-hidden rounded-3xl px-6 py-10 text-white sm:px-12">
            <div className="pointer-events-none absolute inset-0 opacity-[0.06] [background-image:linear-gradient(rgb(255_255_255/0.6)_1px,transparent_1px),linear-gradient(90deg,rgb(255_255_255/0.6)_1px,transparent_1px)] [background-size:40px_40px]" />
            <div className="relative grid items-center gap-8 lg:grid-cols-[1.3fr_1fr]">
              <div className="flex items-start gap-5">
                <span className="hidden h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-primary-500/25 text-primary-200 sm:flex"><Icon name="smartphone" className="h-7 w-7" /></span>
                <div>
                  <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">The Elix app for residents</h2>
                  <p className="mt-2 text-slate-300">Open the gate, answer visitors face to face, invite guests, book facilities and keep the estate&apos;s documents at hand.</p>
                </div>
              </div>
              <div className="lg:justify-self-end"><StoreBadges /></div>
            </div>
          </div>
        </div>
      </section>

      <Section id="how" dark eyebrow="How it works" title="From the lobby to the logbook in seconds"
        intro="Pick a journey and follow it step by step. Drag the scene to look around.">
        <Workflow />
      </Section>

      <Section id="plans" eyebrow="Plans" title="A plan for every estate"
        intro="Priced per site. Tell us your units and gates and we will send a quote. Every plan starts with a 30-day trial.">
        <div className="grid gap-6 lg:grid-cols-3">
          {PLANS.map((p) => (
            <div key={p.name} className={p.highlight
              ? "relative flex flex-col rounded-3xl border-2 border-primary-500 bg-surface p-7 shadow-card"
              : "flex flex-col rounded-3xl border border-line bg-surface p-7 shadow-card"}>
              {p.highlight && <span className="absolute -top-3 left-7 rounded-full bg-primary-500 px-3 py-1 text-xs font-semibold text-white">Most popular</span>}
              <h3 className="text-2xl font-semibold text-ink">{p.name}</h3>
              <p className="mt-1 text-sm text-muted">{p.tagline}</p>
              <ul className="mt-6 flex-1 space-y-3">
                {p.features.map((f) => (
                  <li key={f} className="flex items-start gap-3 text-sm text-body">
                    <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />{f}
                  </li>
                ))}
              </ul>
              <a href={quote(p.name)} className={p.highlight
                ? "mt-8 rounded-xl bg-primary-500 px-5 py-3 text-center font-semibold text-white shadow-primary transition hover:bg-primary-600"
                : "mt-8 rounded-xl border border-line px-5 py-3 text-center font-semibold text-ink transition hover:bg-surface-2"}>
                Contact for quote
              </a>
            </div>
          ))}
        </div>
      </Section>

      <Section id="pdpa" dark eyebrow="PDPA" title="Privacy by design, not by paperwork"
        intro="Built around Singapore's Personal Data Protection Act from the first screen a visitor sees.">
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {PDPA.map(([title, text]) => (
            <div key={title} className="rounded-2xl border border-white/10 bg-white/[0.04] p-6">
              <div className="flex items-center gap-3">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-500/20 text-primary-300"><Icon name="shield" className="h-5 w-5" /></span>
                <h3 className="font-semibold">{title}</h3>
              </div>
              <p className="mt-3 text-sm leading-relaxed text-slate-300">{text}</p>
            </div>
          ))}
        </div>
        <p className="mt-8 text-center text-sm text-slate-300">Read the full <Link href="/privacy/" className="font-medium text-primary-300 underline-offset-4 hover:underline">Privacy policy</Link>.</p>
      </Section>

      <Section id="tech" eyebrow="Technology" title="Built to run quietly every day">
        <div className="grid gap-x-10 gap-y-8 sm:grid-cols-2 lg:grid-cols-3">
          {TECH.map((t) => (
            <div key={t.title} className="flex gap-4">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary-500/10 text-primary-500 dark:text-primary-300"><Icon name={t.icon} className="h-6 w-6" /></span>
              <div>
                <h3 className="font-semibold text-ink">{t.title}</h3>
                <p className="mt-1 text-sm leading-relaxed text-muted">{t.text}</p>
              </div>
            </div>
          ))}
        </div>
      </Section>

      <section id="security" className="scroll-mt-16 bg-canvas">
        <div className="mx-auto max-w-6xl px-4 pb-24 sm:px-6">
          <div className="grid items-center gap-10 rounded-3xl border border-line bg-surface p-8 shadow-card sm:p-12 lg:grid-cols-[1fr_1.2fr]">
            <div>
              <div className="text-sm font-semibold uppercase tracking-widest text-primary-500 dark:text-primary-300">Security</div>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight text-ink">Your residents&apos; data, kept safe</h2>
              <p className="mt-4 text-muted">Access control is a security product. We hold ourselves to the same standard.</p>
              <Link href="/security/" className="mt-6 inline-flex items-center gap-2 font-medium text-primary-500 dark:text-primary-300 hover:underline">
                Read our Cybersecurity policy <Icon name="chevron" className="h-4 w-4" />
              </Link>
            </div>
            <ul className="grid gap-3 sm:grid-cols-2">
              {SECURITY.map((s) => (
                <li key={s} className="flex items-start gap-3 rounded-xl bg-surface-2 p-4 text-sm text-body">
                  <Icon name="lock" className="mt-0.5 h-4 w-4 shrink-0 text-primary-500 dark:text-primary-300" />{s}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* Closing call to action */}
      <section className="brand-panel text-white">
        <div className="mx-auto max-w-4xl px-4 py-20 text-center sm:px-6">
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">See Elix at your estate</h2>
          <p className="mx-auto mt-4 max-w-xl text-lg text-slate-300">A 30-minute walkthrough of the kiosk, the resident app and the dashboard, with your own questions.</p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <a href={DEMO_MAIL} className="rounded-xl bg-primary-500 px-6 py-3.5 font-semibold text-white shadow-primary transition hover:bg-primary-600">Request a demo</a>
            <a href={`mailto:${PRIVACY_EMAIL}`} className="rounded-xl border border-white/20 bg-white/5 px-6 py-3.5 font-semibold text-white transition hover:bg-white/10">{PRIVACY_EMAIL}</a>
          </div>
        </div>
      </section>

      <footer className="border-t border-line bg-canvas">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-4 py-8 sm:flex-row sm:px-6">
          <Credit align="left" className="text-center sm:text-left" />
          <StoreBadges size="sm" />
          <nav className="flex flex-wrap justify-center gap-x-5 gap-y-2 text-sm text-muted">
            <Link href="/privacy/" className="hover:text-ink">Privacy</Link>
            <Link href="/security/" className="hover:text-ink">Cybersecurity</Link>
            <Link href="/account-deletion/" className="hover:text-ink">Delete account</Link>
            <Link href="/login/" className="hover:text-ink">Sign in</Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}

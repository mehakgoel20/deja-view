import type { Metadata } from "next";
import { Suspense } from "react";
import { auth, currentUser } from "@clerk/nextjs/server";
import { ApiStatus } from "@/components/api-status";
import { site } from "@/lib/site";

export const metadata: Metadata = { title: "Dashboard" };

const examples = [
  "Kubernetes pod stuck in CrashLoopBackOff",
  "Redis out of memory errors",
  "High number of 5xx errors after code release",
  "Checkout API returns 502 after the last deploy",
];

// The numbers are the same product facts as on the landing page (see app/page.tsx).
const facts = [
  { value: "2,856", label: "Past incidents it checks against" },
  { value: "5", label: "Closest matches per answer" },
  { value: "10", label: "Recent analyses saved in your browser" },
];

const eyebrow = "font-mono text-xs tracking-widest text-muted uppercase";
const cell = "flex flex-col gap-3 py-8 pr-4 md:px-8 md:first:pl-0";

const heading = "mt-5 text-4xl leading-none font-semibold tracking-tight md:text-7xl md:leading-none";

// Shown at once; the name and email replace it when the user lookup returns.
function WelcomeFallback() {
  return (
    <>
      <h1 className={heading}>Welcome.</h1>
      <p className="mt-5 text-muted">&nbsp;</p>
    </>
  );
}

async function Welcome() {
  await auth.protect();
  const user = await currentUser();
  const email = user?.primaryEmailAddress?.emailAddress;
  const name = user?.firstName ?? user?.fullName ?? user?.username;

  return (
    <>
      <h1 className={heading}>{name ? `Welcome, ${name}.` : "Welcome."}</h1>
      <p className="mt-5 text-muted">{email ?? "\u00a0"}</p>
    </>
  );
}

export default function DashboardPage() {
  return (
    <div className="flex flex-col gap-12 md:gap-16">
      <header>
        <p className={eyebrow}>Dashboard</p>
        <Suspense fallback={<WelcomeFallback />}>
          <Welcome />
        </Suspense>
      </header>

      {/* A plain GET form: the analysis app reads ?q= and starts that analysis.
          The field looks and behaves the same as the one in the analysis app. */}
      <form action={`${site.analyzerUrl}/`} method="get" className="rounded-md border border-line bg-surface">
        <div className="p-5 md:p-6">
          <label htmlFor="q" className={eyebrow}>
            What is going wrong?
          </label>
          <div className="mt-3 flex flex-col gap-3 md:flex-row">
            <div className="flex min-w-0 flex-1 items-center gap-3 rounded-md border border-field bg-paper px-4 py-3 focus-within:border-ink">
              <span aria-hidden="true" className="font-mono text-muted">
                &gt;
              </span>
              <input
                id="q"
                name="q"
                type="text"
                required
                autoComplete="off"
                placeholder="Describe the issue in plain words"
                className="min-w-0 flex-1 bg-transparent text-lg placeholder:text-muted focus:outline-none"
              />
            </div>
            <button
              type="submit"
              className="cursor-pointer rounded-md bg-ink px-6 py-3 font-semibold whitespace-nowrap text-paper hover:bg-brand-dark"
            >
              Analyse
            </button>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 border-t border-line px-5 py-4 md:px-6">
          <span className={`${eyebrow} mr-1`}>Try</span>
          {examples.map((example) => (
            <a
              key={example}
              href={`${site.analyzerUrl}/?q=${encodeURIComponent(example)}`}
              className="rounded-md border border-line px-2.5 py-1 text-sm text-muted hover:border-ink hover:text-ink"
            >
              {example}
            </a>
          ))}
        </div>
      </form>

      <ul className="grid grid-cols-2 border-y border-line md:grid-cols-4 md:divide-x md:divide-line">
        <li className={cell}>
          <p className="text-4xl font-semibold tracking-tight md:text-5xl">
            <ApiStatus url={`${site.apiUrl}/`} />
          </p>
          <p className={eyebrow}>Analysis API</p>
        </li>
        {facts.map((fact) => (
          <li key={fact.label} className={cell}>
            <p className="text-4xl font-semibold tracking-tight tabular-nums md:text-5xl">{fact.value}</p>
            <p className={eyebrow}>{fact.label}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

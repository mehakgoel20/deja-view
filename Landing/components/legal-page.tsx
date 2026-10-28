import type { ReactNode } from "react";
import { Footer } from "@/components/footer";
import { Navbar } from "@/components/navbar";
import { site } from "@/lib/site";

const dateFormat = new Intl.DateTimeFormat("en", { dateStyle: "long", timeZone: "UTC" });

export function LegalPage({ title, children }: { title: string; children: ReactNode }) {
  return (
    <>
      <Navbar />
      <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-16">
        <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">{title}</h1>
        <p className="mt-3 text-sm text-muted">
          Last updated: <time dateTime={site.legal.lastUpdated}>{dateFormat.format(new Date(site.legal.lastUpdated))}</time>
        </p>
        <div className="mt-10 space-y-10">{children}</div>
      </main>
      <Footer />
    </>
  );
}

export function LegalSection({ heading, children }: { heading: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="text-xl font-semibold">{heading}</h2>
      <div className="mt-3 space-y-3 text-ink/90 [&_a]:text-brand [&_a]:underline [&_a]:underline-offset-4 [&_ul]:list-disc [&_ul]:space-y-2 [&_ul]:pl-5">
        {children}
      </div>
    </section>
  );
}

// Shown in place of a legal detail that has not been supplied yet (see lib/site.ts).
export function Missing({ what }: { what: string }) {
  return <strong className="border border-ink bg-surface px-1.5 py-0.5 font-semibold">{what}: to be added before launch</strong>;
}

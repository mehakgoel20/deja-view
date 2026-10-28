import { ButtonLink } from "@/components/button-link";
import { ExamplePanel } from "@/components/example-panel";
import { Footer } from "@/components/footer";
import { Navbar } from "@/components/navbar";
import { ScrollRuler } from "@/components/scroll-ruler";
import { ScrollScene } from "@/components/scroll-scene";

const steps = [
  { label: "Describe", title: "Say what broke.", body: "Plain words. No query language." },
  { label: "Match", title: "It finds the closest past incidents.", body: "Five of them, each scored for relevance." },
  { label: "Answer", title: "Read the causes and fixes.", body: "If nothing matched closely, the answer says so." },
];

// Every number on this page comes from the product itself:
//   2,856  incidents in the search index ("count" in Backend/index/full/manifest.json)
//   5      incidents returned per query (k=5 in Backend/rag/engine.py)
//   10     HISTORY_LIMIT in Frontend/src/App.jsx
const facts = [
  { value: "2,856", label: "past production incidents it checks your issue against" },
  { value: "5", label: "closest matches shown with every answer" },
  { value: "10", label: "recent analyses saved in your browser" },
];

const eyebrow = "font-mono text-xs tracking-widest text-muted uppercase";

export default function Home() {
  return (
    <>
      <Navbar />
      <main className="flex-1">
        <section className="mx-auto flex min-h-[calc(100svh-4rem)] w-full max-w-6xl flex-col justify-between px-4 py-12 md:px-8 md:py-16">
          <div>
            <p className={eyebrow}>Root cause analysis</p>
            <h1 className="mt-6 max-w-4xl text-5xl leading-none font-semibold tracking-tight text-balance md:text-8xl md:leading-none">
              Root causes for on-call engineers.
            </h1>
            <p className="mt-8 max-w-md text-lg text-muted md:text-xl">
              Describe a production issue. Get likely causes and fixes, checked against 2,856 past incidents.
            </p>
          </div>
          <div className="mt-12 flex flex-wrap items-center gap-3">
            <ButtonLink href="/sign-up" size="lg">
              Get started
            </ButtonLink>
            <ButtonLink href="#how-it-works" size="lg" variant="secondary">
              How it works
            </ButtonLink>
          </div>
        </section>

        <ScrollScene id="how-it-works" label="How it works">
          <div className="scene-stage flex items-center">
            <div className="mx-auto grid w-full max-w-6xl grid-cols-1 gap-10 px-4 md:grid-cols-[2fr_3fr] md:items-center md:gap-16 md:px-8">
              <div className="scene-steps min-w-0">
                {steps.map((step, index) => (
                  <div key={step.label} className="scene-step" data-n={index + 1}>
                    <p className={eyebrow}>
                      0{index + 1} / 0{steps.length} <span className="mx-2 text-line">|</span> {step.label}
                    </p>
                    <h2 className="mt-4 text-3xl leading-tight font-semibold tracking-tight md:text-5xl md:leading-tight">
                      {step.title}
                    </h2>
                    <p className="mt-4 text-muted md:text-lg">{step.body}</p>
                  </div>
                ))}
              </div>
              <ExamplePanel />
            </div>
          </div>
        </ScrollScene>

        <section aria-labelledby="numbers-heading" className="border-t border-line">
          <div className="mx-auto w-full max-w-6xl px-4 py-20 md:px-8 md:py-28">
            <h2 id="numbers-heading" className={eyebrow}>
              In numbers
            </h2>
            <ul className="mt-10 grid gap-x-10 gap-y-12 md:grid-cols-3">
              {facts.map((fact) => (
                <li key={fact.label}>
                  <p className="text-6xl font-semibold tracking-tight tabular-nums md:text-8xl">{fact.value}</p>
                  <p className="mt-4 max-w-56 text-muted md:text-lg">{fact.label}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section aria-labelledby="cta-heading" className="border-t border-line">
          <div className="mx-auto flex w-full max-w-6xl flex-col items-start gap-8 px-4 py-24 md:flex-row md:items-end md:justify-between md:px-8 md:py-32">
            <h2 id="cta-heading" className="max-w-2xl text-4xl leading-tight font-semibold tracking-tight md:text-6xl md:leading-tight">
              Have an incident open?
            </h2>
            <ButtonLink href="/sign-up" size="lg">
              Get started
            </ButtonLink>
          </div>
        </section>
      </main>
      <Footer />
      <ScrollRuler />
    </>
  );
}

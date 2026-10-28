"use client";

import { useEffect, useRef } from "react";

const TICKS = 41;

// A small tick ruler in the corner whose marker tracks how far down the page you are.
export function ScrollRuler() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let frame = 0;
    const update = () => {
      frame = 0;
      const distance = document.documentElement.scrollHeight - window.innerHeight;
      const page = distance > 0 ? window.scrollY / distance : 0;
      el.style.setProperty("--page", page.toFixed(4));
      // Step aside at the very bottom so the ruler never covers the footer links.
      el.style.visibility = page > 0.97 ? "hidden" : "visible";
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
    };
  }, []);

  return (
    <div
      ref={ref}
      aria-hidden="true"
      className="pointer-events-none fixed right-8 bottom-8 z-10 hidden rounded-md border border-line bg-surface px-4 py-3 md:block"
    >
      <div className="relative flex h-3 w-60 items-end justify-between">
        {Array.from({ length: TICKS }, (_, index) => (
          <span key={index} className={`w-px bg-muted ${index % 10 === 0 ? "h-3" : "h-1.5 opacity-50"}`} />
        ))}
        <span className="ruler-mark absolute bottom-0 h-3 w-0.5 bg-ink" />
      </div>
    </div>
  );
}

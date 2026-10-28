"use client";

import { useEffect, useRef, type ReactNode } from "react";

const clamp = (n: number) => Math.min(1, Math.max(0, n));

// Pins its stage and reports how far the reader has scrolled through it, as three
// 0 to 1 progress variables (one per step) that the CSS in globals.css animates
// against. Scrolling stays native. With reduced motion nothing is pinned or animated.
export function ScrollScene({ id, label, children }: { id: string; label: string; children: ReactNode }) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    let frame = 0;
    const update = () => {
      frame = 0;
      const rect = el.getBoundingClientRect();
      const distance = rect.height - window.innerHeight;
      const p = distance > 0 ? clamp(-rect.top / distance) : 1;
      el.style.setProperty("--p1", clamp((p - 0.02) / 0.24).toFixed(3));
      el.style.setProperty("--p2", clamp((p - 0.36) / 0.22).toFixed(3));
      el.style.setProperty("--p3", clamp((p - 0.68) / 0.22).toFixed(3));
      el.dataset.step = p < 0.34 ? "1" : p < 0.66 ? "2" : "3";
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };

    el.dataset.live = "";
    update();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      delete el.dataset.live;
    };
  }, []);

  return (
    <section ref={ref} id={id} aria-label={label} className="scene border-t border-line">
      {children}
    </section>
  );
}

"use client";

import { useEffect, useState } from "react";

const labels = { checking: "Checking", online: "Online", offline: "Offline" };

// Asks the analysis API whether it is up, from the visitor's browser.
export function ApiStatus({ url }: { url: string }) {
  const [state, setState] = useState<keyof typeof labels>("checking");

  useEffect(() => {
    const controller = new AbortController();
    fetch(url, { signal: controller.signal })
      .then((response) => setState(response.ok ? "online" : "offline"))
      .catch(() => {
        if (!controller.signal.aborted) setState("offline");
      });
    return () => controller.abort();
  }, [url]);

  return <span aria-live="polite">{labels[state]}</span>;
}

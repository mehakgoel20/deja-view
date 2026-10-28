// Addresses come from environment variables typed into a hosting dashboard, where the
// scheme is easy to leave off. Accept "example.com" as well as "https://example.com".
function address(value: string | undefined, fallback: string) {
  const raw = value?.trim() || fallback;
  const withScheme = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;
  return withScheme.replace(/\/+$/, "");
}

// Single source for brand, contact and legal details used across the site.
export const site = {
  name: "déjà view",
  title: "déjà view: root cause suggestions for on-call engineers",
  description:
    "Describe a production issue in plain words and get likely root causes and fixes, grounded in the closest of 2,856 past production incidents.",
  url: address(process.env.NEXT_PUBLIC_SITE_URL, "http://localhost:3000"),
  analyzerUrl: address(process.env.NEXT_PUBLIC_ANALYZER_URL, "http://127.0.0.1:5173"),
  apiUrl: address(process.env.NEXT_PUBLIC_API_URL, "http://127.0.0.1:8000"),
  legal: {
    owner: "Mehak",
    email: "gmehak350@gmail.com",
    // Not provided yet. Both must be filled in before launch; the legal pages
    // show a visible "to be added" marker while they are null.
    address: null as string | null,
    jurisdiction: null as string | null,
    lastUpdated: "2026-10-10",
  },
};

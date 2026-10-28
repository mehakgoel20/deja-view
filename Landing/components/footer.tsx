import Link from "next/link";
import { site } from "@/lib/site";

// Cached so that reading the clock does not block prerendering; refreshed on revalidation.
async function CopyrightYear() {
  "use cache";
  return new Date().getFullYear();
}

export function Footer() {
  return (
    <footer className="border-t border-line">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 py-8 text-sm text-muted md:px-8 md:flex-row md:items-center md:justify-between">
        <p>
          &copy; <CopyrightYear /> {site.legal.owner}
        </p>
        <nav aria-label="Footer" className="flex flex-wrap gap-x-6 gap-y-2">
          <Link href="/privacy" className="underline-offset-4 hover:text-ink hover:underline">
            Privacy
          </Link>
          <Link href="/terms" className="underline-offset-4 hover:text-ink hover:underline">
            Terms
          </Link>
          <a href={`mailto:${site.legal.email}`} className="underline-offset-4 hover:text-ink hover:underline">
            {site.legal.email}
          </a>
        </nav>
      </div>
    </footer>
  );
}

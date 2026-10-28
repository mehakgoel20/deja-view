import Link from "next/link";
import { site } from "@/lib/site";

export function Logo({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="flex items-center gap-2.5 font-semibold tracking-tight text-ink">
      <svg viewBox="0 0 32 32" width="26" height="26" aria-hidden="true">
        <rect width="32" height="32" rx="7" className="fill-ink" />
        <path d="M16 7v7m0 0-6 9m6-9 6 9" className="stroke-paper" strokeWidth="2.5" strokeLinecap="round" fill="none" />
      </svg>
      <span className="text-lg">{site.name}</span>
    </Link>
  );
}

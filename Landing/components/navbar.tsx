import { Suspense } from "react";
import { Show, UserButton } from "@clerk/nextjs";
import { ButtonLink } from "@/components/button-link";
import { Logo } from "@/components/logo";

const links = [
  { href: "/#how-it-works", label: "How it works" },
];

function SignedOutButtons() {
  return (
    <>
      <ButtonLink href="/sign-in" variant="secondary">
        Sign in
      </ButtonLink>
      <ButtonLink href="/sign-up">Get started</ButtonLink>
    </>
  );
}

function AuthButtons() {
  return (
    <>
      <Show when="signed-out">
        <SignedOutButtons />
      </Show>
      <Show when="signed-in">
        <ButtonLink href="/dashboard" variant="secondary">
          Dashboard
        </ButtonLink>
        <UserButton />
      </Show>
    </>
  );
}

export function Navbar() {
  return (
    <header className="border-b border-line bg-paper">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between gap-4 px-4 md:px-8">
        {/* Signed-in visitors go to their dashboard, everyone else to the landing page. */}
        <Suspense fallback={<Logo />}>
          <Show when="signed-in" fallback={<Logo />}>
            <Logo href="/dashboard" />
          </Show>
        </Suspense>
        <nav aria-label="Main" className="hidden items-center gap-8 font-mono text-xs tracking-widest text-muted uppercase md:flex">
          {links.map((link) => (
            <a key={link.href} href={link.href} className="hover:text-ink">
              {link.label}
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          {/* The signed-out buttons are in the static page; the real state streams in after. */}
          <Suspense fallback={<SignedOutButtons />}>
            <AuthButtons />
          </Suspense>
        </div>
      </div>
    </header>
  );
}

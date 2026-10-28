import type { Metadata } from "next";
import { Suspense } from "react";
import { SignIn } from "@clerk/nextjs";
import { Logo } from "@/components/logo";

export const metadata: Metadata = { title: "Sign in" };

export default function SignInPage() {
  return (
    <main className="flex flex-1 flex-col items-center gap-8 px-4 py-12">
      <Logo />
      {/* Clerk reads the URL, which only exists at request time. */}
      <Suspense>
        <SignIn />
      </Suspense>
    </main>
  );
}

import { Suspense, type ReactNode } from "react";
import { auth } from "@clerk/nextjs/server";
import { Footer } from "@/components/footer";
import { Navbar } from "@/components/navbar";

// Signed-out visitors are redirected to /sign-in before anything under
// /dashboard renders. Pages still run their own check, because layouts do not
// re-render on client-side navigation.
async function SignedInOnly({ children }: { children: ReactNode }) {
  await auth.protect();
  return children;
}

export default function DashboardLayout({ children }: LayoutProps<"/dashboard">) {
  return (
    <>
      <Navbar />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-16 md:px-8">
        <Suspense fallback={<p className="text-muted">Checking your session.</p>}>
          <SignedInOnly>{children}</SignedInOnly>
        </Suspense>
      </main>
      <Footer />
    </>
  );
}

import { clerkMiddleware } from "@clerk/nextjs/server";

// Every route is public by default. /dashboard is protected where it is rendered
// (app/dashboard/layout.tsx and page.tsx), which is where Clerk recommends doing
// auth checks. The sign-in URL below is where those checks send signed-out visitors.
export default clerkMiddleware({
  signInUrl: "/sign-in",
  signUpUrl: "/sign-up",
});

export const config = {
  matcher: [
    // Skip Next.js internals and all static files, unless found in search params
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // Always run for API routes
    "/(api|trpc)(.*)",
    // Always run for Clerk-specific frontend API routes
    "/__clerk/(.*)",
  ],
};

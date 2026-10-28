import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

// Where the logo in the analysis app points. That app runs on another address and
// cannot see the session, so this decides: signed-in visitors go to the dashboard,
// everyone else to the landing page.
export async function GET() {
  const { isAuthenticated } = await auth();
  redirect(isAuthenticated ? "/dashboard" : "/");
}

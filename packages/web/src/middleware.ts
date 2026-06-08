import { clerkMiddleware } from "@clerk/nextjs/server";

// Public demo: every route is open. clerkMiddleware() still attaches Clerk's
// auth context (so ClerkProvider / useUser work for the optional sign-in UI),
// but it protects nothing — there is no auth.protect() call. The product pages
// (/energy, /hazard, /locations) render for anonymous visitors.
export default clerkMiddleware();

export const config = {
  matcher: ["/((?!.*\\..*|_next).*)", "/", "/(api|trpc)(.*)"],
};

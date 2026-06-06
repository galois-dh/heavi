import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

// Public routes: the landing page, the auth pages, and webhooks. Everything else
// (the product modules and their sub-pages) requires an authenticated session —
// frontend-only protection per the Auth + Module Permissioning Spec (Option A).
const isPublicRoute = createRouteMatcher([
  "/",
  "/sign-in(.*)",
  "/sign-up(.*)",
  "/api/webhooks(.*)",
]);

export default clerkMiddleware(async (auth, request) => {
  if (!isPublicRoute(request)) {
    await auth.protect();
  }
});

export const config = {
  matcher: ["/((?!.*\\..*|_next).*)", "/", "/(api|trpc)(.*)"],
};

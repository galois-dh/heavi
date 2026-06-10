# HEAVI AUTHENTICATION + MODULE PERMISSIONING SPEC
# Clerk Integration with Module-Specific Access Control

## Context

Heavi needs user accounts and permissioning before design partner pilots. Requirements:
- Clerk for authentication (already used in the BIM product, familiar)
- Module-specific access: a user may have access to Energy but not Hazard or Locations
- Design partners get specific modules enabled during onboarding
- API endpoints protected (no anonymous scoring)
- Separate Clerk application from the BIM product (independent user bases)

## Architecture

### Clerk Setup

Create a NEW Clerk application for Heavi (not shared with BIM/spatialengine.ai):
- Application name: "Heavi"
- Allowed sign-in methods: email + password, Google OAuth
- Allowed redirect URLs: https://heavi-web.vercel.app/*, http://localhost:3000/*

### Module Permissions Model

Store module access in Clerk user `publicMetadata`:

```json
{
  "modules": ["energy"],           // which modules this user can access
  "plan": "design_partner",        // "design_partner" | "trial" | "paid"
  "pilot_expires": "2026-09-09",   // optional expiry for design partner pilots
  "batch_limit": 200,              // max parcels per batch upload
  "company": "Acme Solar LLC"      // optional company name
}
```

This avoids a separate permissions database. At pre-seed scale (5-20 users), Clerk metadata is sufficient. Migrate to a proper permissions table when user count justifies it.

### Module Access Tiers

| Plan | Modules | Batch Limit | Duration | How Granted |
|---|---|---|---|---|
| design_partner | 1-3 modules (set per user) | 200 | 90 days (pilot_expires) | Danial sets manually in Clerk dashboard |
| trial | energy only | 5 | 14 days | Self-signup (future, not in initial build) |
| paid | 1-3 modules per contract | 200+ | annual | Danial sets manually after contract |

For the initial build, only `design_partner` is needed. Trial and paid tiers are defined for future reference but not implemented.

---

## Frontend Implementation (Next.js)

### Install Clerk

```bash
pnpm add @clerk/nextjs
```

### Environment Variables

```
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_...
CLERK_SECRET_KEY=sk_live_...
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL=/
NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL=/
```

### Middleware (middleware.ts)

Protect all product pages. Public pages: landing page (/), sign-in, sign-up.

```typescript
import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server';

const isPublicRoute = createRouteMatcher([
  '/',
  '/sign-in(.*)',
  '/sign-up(.*)',
  '/api/webhooks(.*)',
]);

export default clerkMiddleware(async (auth, request) => {
  if (!isPublicRoute(request)) {
    await auth.protect();
  }
});

export const config = {
  matcher: ['/((?!.*\\..*|_next).*)', '/', '/(api|trpc)(.*)'],
};
```

### Module-Gated Pages

Each product page checks whether the user has access to that module:

```typescript
// Example: /energy/page.tsx
import { currentUser } from '@clerk/nextjs/server';
import { redirect } from 'next/navigation';

export default async function EnergyPage() {
  const user = await currentUser();
  
  if (!user) {
    redirect('/sign-in');
  }
  
  const modules = (user.publicMetadata?.modules as string[]) || [];
  
  if (!modules.includes('energy')) {
    redirect('/no-access?module=energy');
  }
  
  // Check pilot expiry
  const pilotExpires = user.publicMetadata?.pilot_expires as string;
  if (pilotExpires && new Date(pilotExpires) < new Date()) {
    redirect('/pilot-expired');
  }
  
  // Render the energy page
  return <EnergyPageContent user={user} />;
}
```

### No-Access Page (/no-access)

When a user tries to access a module they don't have:

```
You don't have access to Heavi [Module Name].

Your current plan includes: [list of their modules]

To request access to additional modules, contact dhazarik@gmail.com.
```

### Pilot Expired Page (/pilot-expired)

```
Your design partner pilot has ended.

To continue using Heavi, contact dhazarik@gmail.com to discuss 
annual subscription options.
```

### Landing Page Update

The landing page (/) remains public. When a user is signed in, the product cards should show:
- Modules they have access to: normal card with "Open →" button
- Modules they don't have access to: dimmed card with "Request access →" link
- Not signed in: all cards visible with "Sign in to access →"

### User Menu

Add a Clerk `<UserButton />` in the top nav bar, replacing or alongside the existing nav. Shows the user's avatar, name, and sign-out option.

---

## API Protection

### API Authentication Strategy

The Heavi API (Railway) needs to verify that requests come from authenticated users with the right module access. Two approaches:

**Option A (Simpler, recommended for pre-seed):** Frontend-only protection. The Next.js app gates access to pages and only makes API calls on behalf of authenticated users. The API itself remains unprotected but is not advertised. This works because:
- The API URL is not published
- Rate limiting prevents abuse
- Design partners access through the web UI, not the API directly
- MCP tools can continue working without auth changes

**Option B (More secure, needed for paid tier):** API-level JWT verification. Every API call includes a Clerk session JWT in the Authorization header. The API validates the JWT and checks module permissions. This requires:
- Installing Clerk's Python SDK on the API
- Adding middleware to every endpoint
- Updating the MCP tools to pass auth tokens

**Recommendation:** Start with Option A (frontend-only protection). Add API-level auth when you have paying customers or when the API is published. Document this as a known limitation.

---

## Sign-In / Sign-Up Pages

### /sign-in

Use Clerk's `<SignIn />` component with Heavi branding:

```typescript
import { SignIn } from '@clerk/nextjs';

export default function SignInPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950">
      <div className="text-center mb-8">
        <h1 className="text-2xl font-bold text-white">HEAVI</h1>
        <p className="text-gray-400">Spatial decision intelligence</p>
      </div>
      <SignIn 
        appearance={{
          variables: {
            colorPrimary: '#3b82f6',
            colorBackground: '#111827',
            colorText: '#f9fafb',
            colorInputBackground: '#1f2937',
            colorInputText: '#f9fafb',
          }
        }}
      />
    </div>
  );
}
```

### /sign-up

Same styling with `<SignUp />` component. New sign-ups get NO modules by default — Danial enables modules manually in the Clerk dashboard after onboarding.

Alternatively, for a smoother pilot onboarding: create a Clerk invitation link that pre-sets the user's metadata with the appropriate modules. Clerk supports invitation flows where you can set metadata on the invite.

---

## Design Partner Onboarding Flow

When onboarding a new design partner:

1. **Danial creates an invitation** in Clerk dashboard (or via Clerk API):
   - Set email address
   - Set publicMetadata: `{ modules: ["energy"], plan: "design_partner", pilot_expires: "2026-09-09", batch_limit: 200, company: "Acme Solar LLC" }`

2. **Partner receives email** with sign-up link

3. **Partner creates account** (password or Google)

4. **Partner lands on landing page** → sees Energy module active, Hazard/Locations dimmed

5. **Partner clicks Energy** → full access to solar scoring, batch upload, PDF export, map

### Manual Metadata Update

To change a user's modules after creation:
- Clerk Dashboard → Users → select user → Metadata → edit publicMetadata
- Add or remove modules, change plan, extend pilot_expires

---

## Implementation Sequence

| Step | What | Notes |
|---|---|---|
| 1 | Create Clerk application for Heavi | Dashboard: clerk.com → Create application |
| 2 | Install @clerk/nextjs, add env vars | pnpm add @clerk/nextjs |
| 3 | Add ClerkProvider to layout.tsx | Wraps the entire app |
| 4 | Add middleware.ts with public/protected route matching | Landing, sign-in, sign-up are public; everything else requires auth |
| 5 | Create /sign-in and /sign-up pages with Clerk components | Dark theme matching Heavi UI |
| 6 | Add module permission checking to /energy, /hazard, /locations | Server-side check on publicMetadata.modules |
| 7 | Create /no-access and /pilot-expired pages | Friendly messaging with contact info |
| 8 | Update landing page to show module access state | Active vs dimmed cards based on user metadata |
| 9 | Add UserButton to nav bar | Sign-out, profile management |
| 10 | Update batch scoring to check batch_limit from metadata | Enforce per-user batch limits |

---

## What Danial Needs to Do First (Before Claude Code)

1. Go to https://clerk.com and create a new application called "Heavi"
2. Configure sign-in methods: email + password, Google OAuth
3. Add the redirect URLs:
   - https://heavi-web.vercel.app/*
   - http://localhost:3000/*
4. Copy the Publishable Key (pk_live_...) and Secret Key (sk_live_...)
5. Add both keys to:
   - Vercel environment variables (Settings → Environment Variables)
   - Local .env.local file for development
6. Share the keys with Claude Code (or commit a .env.example with placeholder names)

---

## Acceptance Criteria

1. Unauthenticated user visiting /energy is redirected to /sign-in
2. Unauthenticated user can view the landing page (/)
3. Signed-in user with modules: ["energy"] can access /energy
4. Signed-in user with modules: ["energy"] accessing /hazard is redirected to /no-access
5. Signed-in user with expired pilot_expires is redirected to /pilot-expired
6. Landing page shows active/dimmed cards based on user's module access
7. UserButton visible in nav bar with sign-out option
8. Batch upload respects batch_limit from user metadata
9. /sign-in and /sign-up pages render with dark Heavi theme
10. New sign-up with no metadata has no module access (sees all cards dimmed)

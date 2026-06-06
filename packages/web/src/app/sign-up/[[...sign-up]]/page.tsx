import { SignUp } from "@clerk/nextjs";

// New sign-ups get NO modules by default — Danial enables modules manually in the
// Clerk dashboard (or via an invitation that pre-sets publicMetadata) after
// onboarding. Until then the landing page shows every product card dimmed.
export default function SignUpPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-8 bg-zinc-950 px-6 py-12">
      <div className="text-center">
        <h1 className="text-2xl font-bold tracking-tight text-white">HEAVI</h1>
        <p className="mt-1 text-sm text-zinc-400">Spatial decision intelligence</p>
      </div>
      <SignUp />
    </div>
  );
}

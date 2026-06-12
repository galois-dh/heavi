import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-8 bg-zinc-950 px-6 py-12">
      <div className="text-center">
        <h1 className="text-2xl font-bold tracking-tight text-white">ABELIAN</h1>
        <p className="mt-1 text-sm text-zinc-400">Spatial decision intelligence</p>
      </div>
      <SignIn />
    </div>
  );
}

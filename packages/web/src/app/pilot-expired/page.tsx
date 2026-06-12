import Link from "next/link";

export default function PilotExpiredPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-zinc-950 px-6 py-12 text-center">
      <div className="max-w-md">
        <h1 className="text-xl font-bold text-white">ABELIAN</h1>
        <p className="mt-6 text-lg text-zinc-200">Your design partner pilot has ended.</p>
        <p className="mt-4 text-sm text-zinc-400">
          To continue using Heavi, contact{" "}
          <a href="mailto:dhazarik@gmail.com" className="text-blue-400 hover:text-blue-300">
            dhazarik@gmail.com
          </a>{" "}
          to discuss annual subscription options.
        </p>
        <Link
          href="/"
          className="mt-8 inline-block rounded-md border border-zinc-700 px-4 py-2 text-sm text-zinc-200 transition hover:border-zinc-500 hover:bg-zinc-800"
        >
          ← Back to home
        </Link>
      </div>
    </div>
  );
}

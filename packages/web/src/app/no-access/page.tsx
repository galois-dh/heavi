import Link from "next/link";
import { currentUser } from "@clerk/nextjs/server";
import { MODULE_LABEL, readModuleMeta, type ModuleId } from "../../lib/module-access";

export default async function NoAccessPage({
  searchParams,
}: {
  searchParams: Promise<{ module?: string }>;
}) {
  const { module } = await searchParams;
  const user = await currentUser();
  const meta = readModuleMeta(user?.publicMetadata);
  const moduleName = module
    ? (MODULE_LABEL[module as ModuleId] ?? module[0].toUpperCase() + module.slice(1))
    : "this module";
  const yourModules = (meta.modules ?? []).map(
    (m) => MODULE_LABEL[m as ModuleId] ?? m,
  );

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-zinc-950 px-6 py-12 text-center">
      <div className="max-w-md">
        <h1 className="text-xl font-bold text-white">HEAVI</h1>
        <p className="mt-6 text-lg text-zinc-200">
          You don&apos;t have access to Heavi {moduleName}.
        </p>
        <p className="mt-4 text-sm text-zinc-400">
          Your current plan includes:{" "}
          <span className="text-zinc-200">
            {yourModules.length ? yourModules.join(", ") : "no modules yet"}
          </span>
          .
        </p>
        <p className="mt-4 text-sm text-zinc-400">
          To request access to additional modules, contact{" "}
          <a href="mailto:danial@heavi.ai" className="text-blue-400 hover:text-blue-300">
            danial@heavi.ai
          </a>
          .
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

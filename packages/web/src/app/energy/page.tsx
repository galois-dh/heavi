import { currentUser } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { batchLimitFor, moduleAccessRedirect } from "../../lib/module-access";
import EnergyClient from "./energy-client";

export default async function EnergyPage() {
  const user = await currentUser();
  if (!user) redirect("/sign-in");

  const target = moduleAccessRedirect(user.publicMetadata, "energy");
  if (target) redirect(target);

  return <EnergyClient batchLimit={batchLimitFor(user.publicMetadata)} />;
}

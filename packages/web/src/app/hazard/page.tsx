import { currentUser } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { moduleAccessRedirect } from "../../lib/module-access";
import HazardClient from "./hazard-client";

export default async function HazardPage() {
  const user = await currentUser();
  if (!user) redirect("/sign-in");

  const target = moduleAccessRedirect(user.publicMetadata, "hazard");
  if (target) redirect(target);

  return <HazardClient />;
}

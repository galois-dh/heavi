import { currentUser } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { moduleAccessRedirect } from "../../lib/module-access";
import LocationsClient from "./locations-client";

export default async function LocationsPage() {
  const user = await currentUser();
  if (!user) redirect("/sign-in");

  const target = moduleAccessRedirect(user.publicMetadata, "locations");
  if (target) redirect(target);

  return <LocationsClient />;
}

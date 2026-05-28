"use client";

import { TopNav } from "../../components/top-nav";
import { SpatialWorkspace } from "../../components/spatial-workspace";

export default function SuitabilityPage() {
  return (
    <div className="flex h-full flex-col">
      <TopNav active="suitability" />
      <SpatialWorkspace
        title="Site Suitability"
        subtitle="Alameda County · click the map or ask a question"
        chatPlaceholder="How many buildings are in a flood zone?"
      />
    </div>
  );
}

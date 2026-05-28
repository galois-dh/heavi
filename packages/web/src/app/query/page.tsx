"use client";

import { TopNav } from "../../components/top-nav";
import { SpatialWorkspace } from "../../components/spatial-workspace";

export default function QueryPage() {
  return (
    <div className="flex h-full flex-col">
      <TopNav active="query" />
      <SpatialWorkspace
        title="Spatial Query"
        subtitle="Natural-language PostGIS · power-user tool"
        chatPlaceholder="Show me the 100 highest wildfire risk structures in Santa Rosa"
      />
    </div>
  );
}

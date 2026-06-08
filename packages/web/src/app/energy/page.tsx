import { DEFAULT_BATCH_LIMIT } from "../../lib/module-access";
import EnergyClient from "./energy-client";

// Public demo: no auth gate. Anonymous visitors get the default batch limit.
export default function EnergyPage() {
  return <EnergyClient batchLimit={DEFAULT_BATCH_LIMIT} />;
}

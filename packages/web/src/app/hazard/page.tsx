import HazardClient from "./hazard-client";

// Public demo: no auth gate. Renders for anonymous visitors.
export default function HazardPage() {
  return <HazardClient />;
}

import LocationsClient from "./locations-client";

// Public demo: no auth gate. Renders for anonymous visitors.
export default function LocationsPage() {
  return <LocationsClient />;
}

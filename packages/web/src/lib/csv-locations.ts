/** Parse a CSV of candidate parcels (Month-1 Sprint F2).
 *  Supports: latitude,longitude | lat,lng | address (geocoded) | optional name.
 *  Headerless rows are treated as "lat,lng[,name]" or a bare address.
 *  Validates the 200-row batch limit and required columns. */
export interface CsvLocation {
  latitude?: number;
  longitude?: number;
  address?: string;
  name?: string;
}

export const DEFAULT_BATCH_LIMIT = 200;

export function parseLocationCsv(
  text: string,
  limit: number = DEFAULT_BATCH_LIMIT,
): { rows: CsvLocation[]; error?: string } {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (!lines.length) return { rows: [], error: "The CSV is empty." };

  const first = lines[0].toLowerCase();
  const hasHeader = /lat|lng|lon|long|address|name|site/.test(first) && !/^\s*-?\d/.test(first);
  const header = hasHeader ? lines[0].split(",").map((h) => h.trim().toLowerCase()) : [];
  const col = (names: string[]) => header.findIndex((h) => names.includes(h));
  const latI = col(["latitude", "lat", "y"]);
  const lngI = col(["longitude", "lng", "lon", "long", "x"]);
  const addrI = col(["address", "addr", "location"]);
  const nameI = col(["name", "site", "label", "id"]);

  if (hasHeader && latI < 0 && addrI < 0) {
    return { rows: [], error: "CSV needs latitude/longitude columns or an address column." };
  }

  const dataLines = hasHeader ? lines.slice(1) : lines;
  if (dataLines.length > limit) {
    return { rows: [], error: `Batch limit is ${limit} rows; the CSV has ${dataLines.length}.` };
  }

  const rows: CsvLocation[] = [];
  for (const line of dataLines) {
    const cells = line.split(",").map((c) => c.trim());
    if (hasHeader && latI >= 0) {
      const lat = parseFloat(cells[latI]);
      const lng = parseFloat(cells[lngI]);
      if (Number.isFinite(lat) && Number.isFinite(lng)) {
        rows.push({ latitude: lat, longitude: lng, name: nameI >= 0 ? cells[nameI] : undefined });
      }
    } else if (hasHeader && addrI >= 0) {
      const address = cells[addrI];
      if (address) rows.push({ address, name: nameI >= 0 ? cells[nameI] : undefined });
    } else {
      const m = line.match(/^(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)(?:\s*,\s*(.*))?$/);
      if (m) rows.push({ latitude: parseFloat(m[1]), longitude: parseFloat(m[2]), name: m[3] || undefined });
      else if (line) rows.push({ address: line });
    }
  }
  if (!rows.length) return { rows: [], error: "No valid rows found in the CSV." };
  return { rows };
}

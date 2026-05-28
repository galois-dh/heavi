// Shared client-side "rasterize a DOM element to a one-page PDF" helper.
// Extracted from the original homepage so the suitability workspace and the
// wildfire page can both export panels without duplicating the html2canvas /
// jsPDF / oklch-normalization dance.

// html2canvas's color parser pre-dates CSS Color Level 4, so any oklch(...)
// value blows up. Fix in two passes: rewrite <style> text so Tailwind's
// custom properties and pseudo-element rules emit rgb instead of oklch, then
// pin any remaining oklch computed values as inline styles. html2canvas also
// reads html/body backgrounds directly for the page-background fallback, so
// normalize those too — not just the capture subtree.
function normalizeOklchColors(doc: Document, root: HTMLElement): void {
  const win = doc.defaultView;
  if (!win) return;
  const canvas = doc.createElement("canvas");
  canvas.width = 1;
  canvas.height = 1;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return;

  const toRgb = (text: string): string =>
    text.replace(/oklch\([^)]+\)/gi, (match) => {
      try {
        ctx.clearRect(0, 0, 1, 1);
        ctx.fillStyle = "#000";
        ctx.fillStyle = match;
        ctx.fillRect(0, 0, 1, 1);
        const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data;
        return a === 255
          ? `rgb(${r}, ${g}, ${b})`
          : `rgba(${r}, ${g}, ${b}, ${(a / 255).toFixed(3)})`;
      } catch {
        return match;
      }
    });

  doc.querySelectorAll<HTMLStyleElement>("style").forEach((s) => {
    const t = s.textContent;
    if (t && t.includes("oklch")) s.textContent = toRgb(t);
  });

  const visit = (el: HTMLElement) => {
    const cs = win.getComputedStyle(el);
    for (let i = 0; i < cs.length; i++) {
      const prop = cs[i];
      const val = cs.getPropertyValue(prop);
      if (val.includes("oklch")) {
        el.style.setProperty(prop, toRgb(val));
      }
    }
  };

  if (doc.documentElement) visit(doc.documentElement);
  if (doc.body) visit(doc.body);
  visit(root);
  root.querySelectorAll<HTMLElement>("*").forEach(visit);
}

export async function exportElementToPdf(el: HTMLElement, filename: string): Promise<void> {
  const [{ default: html2canvas }, jsPDFModule] = await Promise.all([
    import("html2canvas"),
    import("jspdf"),
  ]);
  const canvas = await html2canvas(el, {
    backgroundColor: "#ffffff",
    scale: 2,
    useCORS: true,
    logging: false,
    onclone: (doc, cloned) => {
      normalizeOklchColors(doc, cloned as HTMLElement);
    },
  });
  const imgData = canvas.toDataURL("image/png");
  const pdf = new jsPDFModule.jsPDF({ unit: "pt", format: "letter", orientation: "portrait" });
  const pageW = pdf.internal.pageSize.getWidth();
  const pageH = pdf.internal.pageSize.getHeight();
  const margin = 32;
  const maxW = pageW - margin * 2;
  const maxH = pageH - margin * 2;
  const ratio = Math.min(maxW / canvas.width, maxH / canvas.height);
  const drawW = canvas.width * ratio;
  const drawH = canvas.height * ratio;
  pdf.addImage(imgData, "PNG", (pageW - drawW) / 2, margin, drawW, drawH);
  pdf.save(filename);
}

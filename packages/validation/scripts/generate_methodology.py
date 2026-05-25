"""Standalone methodology-doc regeneration (no DB needed)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from heavi_validation.methodology import generate_methodology  # noqa: E402
from modules.site_suitability import METADATA  # noqa: E402


def main() -> int:
    doc = generate_methodology(METADATA)
    out = ROOT / "reports" / "site_suitability_methodology.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc.markdown)
    print(f"wrote {out}")
    print(f"hash:  {doc.version_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

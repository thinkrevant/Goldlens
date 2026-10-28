"""Export the real GoldLens numbers the landing site animates.

    python scripts/export_site_data.py

Writes site/data.js so the landing page also works as plain static files (e.g. GitHub Pages).
When the site is served by `python -m goldlens.web`, /data.js is generated live instead.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from goldlens.pipeline import build_workspace  # noqa: E402
from goldlens.sitedata import build_site_data  # noqa: E402


def main():
    data = build_site_data(build_workspace())
    out = ROOT / "site" / "data.js"
    out.parent.mkdir(exist_ok=True)
    out.write_text("window.GOLDLENS = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n", encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()

"""Part 3: data/values.csv -> Google Sheet (gspread) or .xlsx fallback."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from draftboard import ROOT, load_config  # noqa: E402
from draftboard.board import build_workbook  # noqa: E402
from draftboard.valuation import display_stats  # noqa: E402


def load_workbook_model(cfg: dict):
    vals = pd.read_csv(ROOT / cfg["paths"]["values"], keep_default_na=False)
    nt = cfg["league"]["num_teams"]
    vals = vals.sort_values(f"value{nt}", ascending=False).head(cfg["board"]["max_players"])
    vals = vals.sort_values("name", key=lambda s: s.str.lower()).reset_index(drop=True)
    sched_path = cfg["paths"].get("schedule")
    schedule = None
    if sched_path and (ROOT / sched_path).exists():
        schedule = pd.read_csv(ROOT / sched_path, keep_default_na=False)
    return build_workbook(vals, display_stats(vals), cfg, schedule)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=None)
    ap.add_argument("--xlsx", action="store_true", help="write the .xlsx fallback instead of the API")
    args = ap.parse_args()
    cfg = load_config(args.config)
    wb = load_workbook_model(cfg)
    if args.xlsx:
        from draftboard.xlsx import render
        out = render(wb, ROOT / cfg["paths"]["xlsx"])
        print(f"wrote {out}")
        return
    from draftboard.gsheet import open_spreadsheet, render
    ss = open_spreadsheet(cfg, ROOT)
    render(wb, ss)
    print(f"rebuilt {ss.url}")


if __name__ == "__main__":
    main()

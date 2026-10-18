"""Part 1 + 2: raw tables -> data/players.csv -> data/values.csv (z's for every team count)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draftboard import ROOT, load_config  # noqa: E402
from draftboard.ingest import build_players, dedupe_names  # noqa: E402
from draftboard.valuation import CATS, value_all  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=None)
    ap.add_argument("--skip-ingest", action="store_true", help="reuse existing data/players.csv")
    args = ap.parse_args()
    cfg = load_config(args.config)
    paths = cfg["paths"]

    import pandas as pd
    if args.skip_ingest:
        players = pd.read_csv(ROOT / paths["players"], keep_default_na=False)
    else:
        players = dedupe_names(build_players(cfg, ROOT))
        players.to_csv(ROOT / paths["players"], index=False)
        print(f"wrote {paths['players']} ({len(players)} players)")

    lg = cfg["league"]
    vals = value_all(players, lg["team_count_options"], lg["rounds"], cfg["valuation"])
    nt = lg["num_teams"]
    vals = vals.sort_values(f"value{nt}", ascending=False).reset_index(drop=True)
    vals.to_csv(ROOT / paths["values"], index=False)
    print(f"wrote {paths['values']}")

    show = vals.head(25)
    print(f"\nTop 25 by value ({nt} teams):")
    for i, r in show.iterrows():
        cats = " ".join(f"{r[f'z{nt}_{c}']:+5.1f}" for c in CATS)
        print(f"  {i + 1:3d}. {r['name']:26} {r['yahoo_positions']:6} {r[f'value{nt}']:6.2f}  "
              f"ADP {r['adp']:6.1f}   {cats}")
    print("        (cats: " + " ".join(CATS) + ")")


if __name__ == "__main__":
    main()

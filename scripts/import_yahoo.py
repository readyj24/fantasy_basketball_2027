"""Pasted Yahoo draft-room list -> data/raw/adp.csv + data/raw/yahoo_rank.csv.

ADP        = Yahoo L7ADP (last 7 days of real drafts), falling back to XRank.
Yahoo rank = XRank, the draft room's default order.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from draftboard import ROOT, load_config  # noqa: E402
from draftboard.ingest import load_projections  # noqa: E402
from draftboard.yahoo import match_to_projections, parse_board  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paste", nargs="?", default="data/raw/yahoo_board.txt")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()
    cfg = load_config(args.config)
    board = parse_board((ROOT / args.paste).read_text(encoding="utf-8"))
    proj = load_projections(ROOT / cfg["paths"]["projections"])
    board["name"] = match_to_projections(board, proj)
    miss = board[board["name"].isna()]
    print(f"{len(board)} Yahoo players, {len(board) - len(miss)} matched to projections")
    for _, r in miss.iterrows():
        print(f"  unmatched: {r['yahoo_name']} ({r['team']}, XRank {r['xrank']})")
    ok = board.dropna(subset=["name"])
    adp = pd.DataFrame({"Player": ok["name"], "ADP": ok["l7adp"].fillna(ok["xrank"]),
                        "XRank": ok["xrank"], "L7ADP": ok["l7adp"], "Rank": ok["rank"],
                        "Status": ok["status"]})
    adp.to_csv(ROOT / cfg["paths"]["adp"], index=False)
    yr = pd.DataFrame({"Player": ok["name"], "Rank": ok["xrank"], "Pos": ok["positions"]})
    yr.to_csv(ROOT / cfg["paths"]["yahoo_rank"], index=False)
    print(f"wrote {cfg['paths']['adp']} and {cfg['paths']['yahoo_rank']}")
    inj = ok[ok["status"].isin(["O", "INJ", "NA"])]
    if len(inj):
        print("out / NA:", ", ".join(f"{n} ({s})" for n, s in zip(inj["name"], inj["status"])))


if __name__ == "__main__":
    main()

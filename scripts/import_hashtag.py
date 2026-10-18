"""Saved Hashtag Basketball page (.html) -> data/raw/projections.csv (+ hashtag ADP)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draftboard import ROOT, load_config  # noqa: E402
from draftboard.hashtag import parse_html, selected_options  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("html")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()
    cfg = load_config(args.config)
    opts = selected_options(args.html)
    print("page settings:", {k: opts[k] for k in ("DDDURATION", "DDSHOW", "DDPOSFROM", "DDRANK") if k in opts})
    df = parse_html(args.html)
    out = ROOT / cfg["paths"]["projections"]
    out.parent.mkdir(parents=True, exist_ok=True)
    df.drop(columns=[c for c in ("ADP",) if c in df]).to_csv(out, index=False)
    print(f"wrote {out} ({len(df)} players)")
    if "ADP" in df:
        adp = df[["PLAYER", "ADP"]].copy()
        adp_out = ROOT / "data/raw/adp_hashtag.csv"
        adp.to_csv(adp_out, index=False)
        print(f"wrote {adp_out} (Hashtag's ADP column, {adp['ADP'].ne('').sum()} non-blank)")


if __name__ == "__main__":
    main()

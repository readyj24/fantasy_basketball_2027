"""Fit the Punt Advisor's per-category noise factors (config noise.phi) from game logs.

Input: one row per player-game, e.g. NBA.com leaguegamelog (PlayerOrTeam=P) or any CSV
with columns PLAYER_ID (or PLAYER_NAME), MIN, PTS, REB, AST, STL, BLK, TOV, FG3M, FGM,
FGA, FTM, FTA. For each category, phi = pooled game-to-game variance / the base used in
valuation.category_noise:

  counting stats: var(x) / mean(x)                       (1 = Poisson)
  FG% / FT%:      var(m - p*a) / (mean(a) * p * (1-p))   (1 = make/miss luck only;
                  > 1 adds shot-volume swings, p = league rate)

Only regulars count (>= 30 games, >= 20 minutes). Prints the phi block for config.yaml.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


# Kaggle "Historical NBA Data and Player Box Scores" (PlayerStatistics.csv) column names
KAGGLE = {"personId": "PLAYER_ID", "numMinutes": "MIN", "points": "PTS", "reboundsTotal": "REB",
          "assists": "AST", "steals": "STL", "blocks": "BLK", "turnovers": "TOV",
          "threePointersMade": "FG3M", "fieldGoalsMade": "FGM", "fieldGoalsAttempted": "FGA",
          "freeThrowsMade": "FTM", "freeThrowsAttempted": "FTA"}


def load_kaggle(path: str, season_start: str, season_end: str) -> pd.DataFrame:
    """One regular season out of the all-history PlayerStatistics.csv."""
    cols = list(KAGGLE) + ["firstName", "lastName", "gameId", "gameDateTimeEst", "gameType",
                           "playerteamName"]
    df = pd.read_csv(path, usecols=cols, low_memory=False)
    d = pd.to_datetime(df["gameDateTimeEst"], errors="coerce")
    df = df[(d >= season_start) & (d <= season_end) & (df["gameType"] == "Regular Season")].copy()
    df["gameDate"] = d[df.index]
    return df.rename(columns=KAGGLE)


def fit(df: pd.DataFrame, min_games: int = 30, min_minutes: float = 20) -> dict[str, float]:
    df = df.rename(columns=lambda c: c if c in ("gameDate", "firstName", "lastName") else c.upper())
    pid = "PLAYER_ID" if "PLAYER_ID" in df else "PLAYER_NAME"
    df = df[pd.to_numeric(df["MIN"], errors="coerce").fillna(0) > 0]
    g = df.groupby(pid)
    keep = g.size()[g.size() >= min_games].index
    mins = g["MIN"].apply(lambda s: pd.to_numeric(s, errors="coerce").mean())
    keep = keep.intersection(mins[mins >= min_minutes].index)
    df = df[df[pid].isin(keep)]
    g = df.groupby(pid)
    phi = {}
    for col, key in (("PTS", "pts"), ("REB", "reb"), ("AST", "ast"), ("STL", "stl"),
                     ("BLK", "blk"), ("FG3M", "fg3m"), ("TOV", "tov")):
        phi[key] = float(g[col].var(ddof=1).sum() / g[col].mean().sum())
    for m, a, key in (("FGM", "FGA", "fg_pct"), ("FTM", "FTA", "ft_pct")):
        p = df[m].sum() / df[a].sum()
        imp = df[m] - p * df[a]
        phi[key] = float(imp.groupby(df[pid]).var(ddof=1).sum() / (g[a].mean() * p * (1 - p)).sum())
    return phi


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--season", default="2025-10-01:2026-04-30",
                    help="date range when the file is Kaggle's all-history PlayerStatistics.csv")
    args = ap.parse_args()
    head = pd.read_csv(args.csv, nrows=1)
    if "personId" in head.columns:
        a, b = args.season.split(":")
        df = load_kaggle(args.csv, a, b)
        print(f"{len(df)} player-games {a}..{b}", file=sys.stderr)
    else:
        df = pd.read_csv(args.csv)
    phi = fit(df)
    print("noise:\n  phi:")
    for k, v in phi.items():
        print(f"    {k}: {v:.2f}")
    print("\nPaste into config.yaml, then: python scripts/build_sheet.py", file=sys.stderr)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    main()

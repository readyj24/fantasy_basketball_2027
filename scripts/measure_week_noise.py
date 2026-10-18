"""Measure weekly H2H noise per category directly from a season of game logs.

Random 14-man rosters of regulars are scored week by week (Mon-Sun) on the real
2025-26 schedule, counting at most 10 players per day (active lineup slots). For each
category the week-to-week SD of a roster's total -- including 3- vs 4-game weeks,
DNPs, shot-volume and lineup-mix swings, minus league-wide week effects that hit both
teams in a matchup alike -- is converted to z units:

    sigma_week(z) = sqrt(2) * SD(weekly total) / (G * s_c)

(sqrt(2): two independent teams; G = counted games per roster spot per week; s_c = the
pool SD of the per-game stat from the current projections, i.e. the z scale). Prints a
`measured` block for config.yaml (noise:) that replaces the modelled weekly part.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from draftboard import ROOT, load_config  # noqa: E402
from draftboard.valuation import CATS, COUNTING  # noqa: E402
from scripts.fit_noise import load_kaggle  # noqa: E402


def pool_scales(vals: pd.DataFrame, n: int) -> dict[str, float]:
    pool = vals[vals[f"pool{n}"].astype(str).str.lower() == "true"]
    p_fg = pool["fgm"].sum() / pool["fga"].sum()
    p_ft = pool["ftm"].sum() / pool["fta"].sum()
    r = pool["ast"].sum() / pool["tov"].sum()
    s = {c: float(pool[c].std(ddof=0)) for c in COUNTING}
    s["fg_pct"] = float((pool["fgm"] - p_fg * pool["fga"]).std(ddof=0))
    s["ft_pct"] = float((pool["ftm"] - p_ft * pool["fta"]).std(ddof=0))
    s["a_to"] = float((pool["ast"] - r * pool["tov"]).std(ddof=0))
    return s


def measure(gl: pd.DataFrame, scales: dict[str, float], rounds: int = 14, slots: int = 10,
            n_rosters: int = 400, regulars: int = 200, seed: int = 0) -> pd.DataFrame:
    gl = gl.copy()
    gl["day"] = gl["gameDate"].dt.normalize()
    gl["week"] = gl["day"].dt.to_period("W-SUN")
    # Regulars: most total minutes (a stand-in for a fantasy-relevant pool).
    mins = gl.groupby("PLAYER_ID")["MIN"].sum().sort_values(ascending=False)
    ids = mins.index[:regulars].to_numpy()
    gl = gl[gl["PLAYER_ID"].isin(ids)]
    p_fg = gl["FGM"].sum() / gl["FGA"].sum()
    p_ft = gl["FTM"].sum() / gl["FTA"].sum()
    r = gl["AST"].sum() / gl["TOV"].sum()
    stat = pd.DataFrame({
        "fg3m": gl["FG3M"], "pts": gl["PTS"], "reb": gl["REB"], "ast": gl["AST"],
        "stl": gl["STL"], "blk": gl["BLK"],
        "fg_pct": gl["FGM"] - p_fg * gl["FGA"], "ft_pct": gl["FTM"] - p_ft * gl["FTA"],
        "a_to": gl["AST"] - r * gl["TOV"],
    }, index=gl.index)
    # Drop partial first/last weeks and the All-Star week (fewest games).
    wk_games = gl.groupby("week").size()
    weeks = wk_games[wk_games >= 0.6 * wk_games.median()].index[1:-1]
    gl, stat = gl[gl["week"].isin(weeks)], stat.loc[gl[gl["week"].isin(weeks)].index]
    rng = np.random.default_rng(seed)
    totals, games = [], []
    for _ in range(n_rosters):
        roster = rng.choice(ids, rounds, replace=False)
        m = gl["PLAYER_ID"].isin(roster)
        g, st = gl[m], stat[m]
        # At most `slots` players count per day: keep a random subset on crowded days.
        rank = g.assign(u=rng.random(len(g))).groupby("day")["u"].rank(method="first")
        keep = rank <= slots
        g, st = g[keep], st[keep]
        totals.append(st.groupby(g["week"]).sum().reindex(weeks, fill_value=0))
        games.append(g.groupby("week").size().reindex(weeks, fill_value=0).mean() / rounds)
    # Remove league-wide week effects (light/heavy weeks hit both teams in a matchup alike):
    # demean each week across rosters before taking each roster's week-to-week SD.
    week_mean = sum(totals) / len(totals)
    sd = pd.concat([(t - week_mean).std(ddof=1) for t in totals], axis=1).mean(axis=1)
    G = float(np.mean(games))
    out = pd.DataFrame({"weekly_sd": sd, "s_c": pd.Series(scales)})
    out["sigma_week_z"] = np.sqrt(2) * out["weekly_sd"] / (G * out["s_c"])
    out.attrs["G"] = G
    return out.loc[CATS]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--season", default="2025-10-01:2026-04-30")
    ap.add_argument("--teams", type=int, default=14)
    args = ap.parse_args()
    cfg = load_config()
    a, b = args.season.split(":")
    gl = load_kaggle(args.csv, a, b)
    gl["MIN"] = pd.to_numeric(gl["MIN"], errors="coerce").fillna(0)
    gl = gl[gl["MIN"] > 0]
    vals = pd.read_csv(ROOT / cfg["paths"]["values"], keep_default_na=False)
    res = measure(gl, pool_scales(vals, args.teams), rounds=cfg["league"]["rounds"])
    print(f"counted games per roster spot per week: {res.attrs['G']:.2f}", file=sys.stderr)
    print(res.round(3).to_string(), file=sys.stderr)
    print("  measured:                     # scripts/measure_week_noise.py (2025-26 game logs)")
    print(f"    games_per_spot: {res.attrs['G']:.2f}")
    print("    weekly_sd:")
    for c, v in res["weekly_sd"].items():
        print(f"      {c}: {v:.3f}")


if __name__ == "__main__":
    main()

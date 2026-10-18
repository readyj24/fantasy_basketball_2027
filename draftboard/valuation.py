"""Per-category z-score valuation (H2H 9-cat with A/T instead of TO).

All category values are per game. For each team count the pool is the top
NumTeams x rounds players; replacement level is the player(s) just outside it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CATS = ["fg_pct", "ft_pct", "fg3m", "pts", "reb", "ast", "stl", "blk", "a_to"]
CAT_LABELS = {
    "fg_pct": "FG%", "ft_pct": "FT%", "fg3m": "3PTM", "pts": "PTS", "reb": "REB",
    "ast": "AST", "stl": "STL", "blk": "BLK", "a_to": "A/T",
}
COUNTING = ["fg3m", "pts", "reb", "ast", "stl", "blk"]


def pct_impact(made: np.ndarray, att: np.ndarray, pool_pct: float) -> np.ndarray:
    """Volume-weighted percentage impact: att x (made/att - pool%) = made - att x pool%."""
    return made - att * pool_pct


def a_to_impact(ast: np.ndarray, tov: np.ndarray, pool_ratio: float) -> np.ndarray:
    """A/T impact: AST - r x TO with r = pool-wide AST/TO."""
    return ast - pool_ratio * tov


def raw_impacts(df: pd.DataFrame, pool: pd.Series) -> pd.DataFrame:
    """Category inputs before z-scoring; pool = boolean mask defining league averages."""
    p = df[pool]
    fg = p["fgm"].sum() / p["fga"].sum()
    ft = p["ftm"].sum() / p["fta"].sum()
    r = p["ast"].sum() / p["tov"].sum()
    out = df[COUNTING].astype(float).copy()
    out["fg_pct"] = pct_impact(df["fgm"].to_numpy(float), df["fga"].to_numpy(float), fg)
    out["ft_pct"] = pct_impact(df["ftm"].to_numpy(float), df["fta"].to_numpy(float), ft)
    out["a_to"] = a_to_impact(df["ast"].to_numpy(float), df["tov"].to_numpy(float), r)
    return out[CATS]


def availability(games: pd.Series, full: float, exponent: float) -> pd.Series:
    return np.minimum(1.0, games.astype(float).clip(lower=0) / full) ** exponent


def zscores(df: pd.DataFrame, pool: pd.Series, avail: pd.Series) -> pd.DataFrame:
    imp = raw_impacts(df, pool)
    mu = imp[pool].mean()
    sd = imp[pool].std(ddof=0).replace(0, 1.0)
    return ((imp - mu) / sd).mul(avail, axis=0)


def value_players(df: pd.DataFrame, pool_size: int, vcfg: dict) -> pd.DataFrame:
    """Return per-category surplus z's (replacement level subtracted) and pool flag."""
    df = df.reset_index(drop=True)
    if len(df) <= pool_size:
        raise ValueError(f"need more than {pool_size} projected players, have {len(df)}")
    avail = availability(df["games"], vcfg["full_season_games"], vcfg["availability_exponent"])

    # Seed pool: everyone with a meaningful role, then iterate rank -> re-pool -> recompute.
    pool = pd.Series(True, index=df.index)
    z = zscores(df, pool, avail)
    for _ in range(int(vcfg.get("iterations", 2))):
        order = z.sum(axis=1).sort_values(ascending=False).index
        pool = pd.Series(False, index=df.index)
        pool.loc[order[:pool_size]] = True
        z = zscores(df, pool, avail)

    order = z.sum(axis=1).sort_values(ascending=False).index
    window = max(1, int(vcfg.get("replacement_window", 1)))
    repl_idx = order[pool_size:pool_size + window]
    replacement = z.loc[repl_idx].mean()
    surplus = z - replacement

    in_pool = pd.Series(False, index=df.index)
    in_pool.loc[order[:pool_size]] = True
    surplus["in_pool"] = in_pool
    return surplus


def value_all(players: pd.DataFrame, team_counts: list[int], rounds: int, vcfg: dict) -> pd.DataFrame:
    """players + z{N}_{cat} and pool{N} columns for every team count."""
    out = players.reset_index(drop=True).copy()
    for n in team_counts:
        v = value_players(out, n * rounds, vcfg)
        for c in CATS:
            out[f"z{n}_{c}"] = v[c].round(4)
        out[f"pool{n}"] = v["in_pool"]
        out[f"value{n}"] = v[CATS].sum(axis=1).round(4)
    return out


def display_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Per-game projections shown on the board, in category order."""
    return pd.DataFrame({
        "fg_pct": (df["fgm"] / df["fga"]).round(3),
        "ft_pct": (df["ftm"] / df["fta"].replace(0, np.nan)).round(3),
        "fg3m": df["fg3m"].round(1), "pts": df["pts"].round(1), "reb": df["reb"].round(1),
        "ast": df["ast"].round(1), "stl": df["stl"].round(1), "blk": df["blk"].round(1),
        "a_to": (df["ast"] / df["tov"].replace(0, np.nan)).round(2),
    }).fillna(0)

"""Per-category z-score valuation (H2H 9-cat with A/T instead of TO).

All category values are per game. For each team count the pool is the top
NumTeams x rounds players; replacement level comes from a few players per position
ranked just below the bottom of the pool (see replacement_line).
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


POSITIONS = ("G", "F", "C")


def position_lines(df: pd.DataFrame, z: pd.DataFrame, order: pd.Index, pool_size: int,
                   vcfg: dict) -> dict[str, pd.Series]:
    """Per-position replacement line: mean z of the first `replacement_per_position` players
    eligible at that position, ranked from pool_size + replacement_start_offset onward."""
    start = max(0, pool_size + int(vcfg.get("replacement_start_offset", 0)))
    k = max(1, int(vcfg.get("replacement_per_position", 5)))
    below = order[start:]
    lines = {}
    for p in POSITIONS:
        elig = [i for i in below if p in str(df.at[i, "yahoo_positions"]).split(",")][:k]
        if elig:
            lines[p] = z.loc[elig].mean()
    return lines


def replacement_line(df: pd.DataFrame, z: pd.DataFrame, order: pd.Index, pool_size: int,
                     vcfg: dict) -> pd.DataFrame:
    """Row-aligned replacement z's to subtract from every player.

    blended:    one line for everyone = average of the G, F and C lines.
    positional: each player is measured against the easiest-to-beat line among his
                eligible positions (lowest replacement total), i.e. classic VORP.
    """
    lines = position_lines(df, z, order, pool_size, vcfg)
    blended = pd.concat(lines.values(), axis=1).mean(axis=1)
    if vcfg.get("replacement_mode", "blended") != "positional":
        return pd.DataFrame([blended.values] * len(df), index=df.index, columns=z.columns)
    rows = []
    for i in df.index:
        cands = [lines[p] for p in str(df.at[i, "yahoo_positions"]).split(",") if p in lines]
        rows.append(min(cands, key=lambda s: s.sum()) if cands else blended)
    return pd.DataFrame([r.values for r in rows], index=df.index, columns=z.columns)


def pooled_zscores(df: pd.DataFrame, pool_size: int, vcfg: dict) -> tuple[pd.DataFrame, pd.Index]:
    """Availability-adjusted z's against the iterated top-`pool_size` pool, plus rank order."""
    if len(df) <= pool_size:
        raise ValueError(f"need more than {pool_size} projected players, have {len(df)}")
    avail = availability(df["games"], vcfg["full_season_games"], vcfg["availability_exponent"])
    pool = pd.Series(True, index=df.index)        # seed: everyone; then rank -> re-pool -> recompute
    z = zscores(df, pool, avail)
    for _ in range(int(vcfg.get("iterations", 2))):
        order = z.sum(axis=1).sort_values(ascending=False).index
        pool = pd.Series(False, index=df.index)
        pool.loc[order[:pool_size]] = True
        z = zscores(df, pool, avail)
    return z, z.sum(axis=1).sort_values(ascending=False).index


def value_players(df: pd.DataFrame, pool_size: int, vcfg: dict) -> pd.DataFrame:
    """Return per-category surplus z's (replacement level subtracted) and pool flag."""
    df = df.reset_index(drop=True)
    z, order = pooled_zscores(df, pool_size, vcfg)
    surplus = z - replacement_line(df, z, order, pool_size, vcfg)
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


def category_noise(vals: pd.DataFrame, n: int, rounds: int, ncfg: dict) -> pd.DataFrame:
    """Weekly H2H noise per category, in the same units as summed surplus z's.

    For a matchup, P(win cat) ~ Phi(projected z edge / sigma). sigma combines:
      week:  game-to-game randomness of both teams' weekly totals. Each player-game's
             variance = phi_c x base, where base is the mean (counting stats), the binomial
             att x p(1-p) (FG%/FT% impact), or AST + r^2 TO (A/T impact); phi_c (>= 1)
             inflates that for streakiness, shot-volume and lineup-mix swings.
      teams: how much a random opponent's roster differs from the average team.
    Converting weekly totals to z units: expected weekly edge = G x s_c x z-edge, with
    G = counted games per roster spot per week and s_c the pool sd of the per-game stat.
    """
    pool = vals[vals[f"pool{n}"].astype(str).str.lower() == "true"]
    phi = ncfg["phi"]
    G = ncfg["weekly_games_per_player"]
    p_fg = pool["fgm"].sum() / pool["fga"].sum()
    p_ft = pool["ftm"].sum() / pool["fta"].sum()
    r = pool["ast"].sum() / pool["tov"].sum()
    per_game = {c: pool[c].astype(float) for c in COUNTING}
    per_game["fg_pct"] = pool["fgm"] - pool["fga"] * p_fg
    per_game["ft_pct"] = pool["ftm"] - pool["fta"] * p_ft
    per_game["a_to"] = pool["ast"] - r * pool["tov"]
    var = {c: phi[c] * pool[c].astype(float) for c in COUNTING}
    var["fg_pct"] = phi["fg_pct"] * pool["fga"] * p_fg * (1 - p_fg)
    var["ft_pct"] = phi["ft_pct"] * pool["fta"] * p_ft * (1 - p_ft)
    var["a_to"] = phi["ast"] * pool["ast"] + r ** 2 * phi["tov"] * pool["tov"]
    rows = []
    for c in CATS:
        s = per_game[c].std(ddof=0)
        week = np.sqrt(2 * rounds * var[c].mean() / G) / s
        teams = ncfg["team_spread_factor"] * np.sqrt(rounds) * pool[f"z{n}_{c}"].astype(float).std(ddof=0)
        rows.append({"cat": c, "week": week, "teams": teams, "sigma": float(np.hypot(week, teams))})
    return pd.DataFrame(rows).set_index("cat")

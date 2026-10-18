import numpy as np
import pandas as pd
import pytest

from draftboard.valuation import (CATS, a_to_impact, availability, pct_impact, pooled_zscores,
                                  position_lines, raw_impacts, value_all, value_players)

VCFG = {"full_season_games": 75, "availability_exponent": 0.5, "iterations": 2,
        "replacement_start_offset": -16, "replacement_per_position": 5,
        "replacement_mode": "blended"}


def test_fg_impact_hand_calc():
    # Player A: 10/20 (50%), Player B: 3/10 (30%). Pool FG% = 13/30 = 0.4333...
    made, att = np.array([10.0, 3.0]), np.array([20.0, 10.0])
    pool = made.sum() / att.sum()
    imp = pct_impact(made, att, pool)
    # A: 20 x (0.5 - 0.43333) = +1.3333 ; B: 10 x (0.3 - 0.43333) = -1.3333
    assert imp == pytest.approx([20 * (0.5 - 13 / 30), 10 * (0.3 - 13 / 30)])
    assert imp == pytest.approx([4 / 3, -4 / 3])
    assert imp.sum() == pytest.approx(0)          # volume-weighted impacts net to zero over the pool


def test_ft_impact_hand_calc():
    # 90% on 8 FTA vs pool 78% -> 8 x 0.12 = +0.96 ; 50% on 10 FTA -> 10 x -0.28 = -2.8
    assert pct_impact(np.array([7.2, 5.0]), np.array([8.0, 10.0]), 0.78) == pytest.approx([0.96, -2.8])


def test_a_to_impact_hand_calc():
    # Pool: AST 8+2 = 10, TO 2+3 = 5 -> r = 2. A: 8 - 2x2 = +4 ; B: 2 - 2x3 = -4
    ast, tov = np.array([8.0, 2.0]), np.array([2.0, 3.0])
    r = ast.sum() / tov.sum()
    assert r == 2
    assert a_to_impact(ast, tov, r) == pytest.approx([4.0, -4.0])


def test_raw_impacts_use_pool_averages():
    df = pd.DataFrame({"fgm": [10, 3, 1], "fga": [20, 10, 10], "ftm": [4, 4, 1], "fta": [5, 5, 4],
                       "ast": [8, 2, 0], "tov": [2, 3, 9], "fg3m": [1, 2, 0], "pts": [20, 10, 5],
                       "reb": [5, 5, 5], "stl": [1, 1, 1], "blk": [1, 0, 0]}, dtype=float)
    pool = pd.Series([True, True, False])          # third player excluded from averages
    imp = raw_impacts(df, pool)
    assert imp.loc[0, "fg_pct"] == pytest.approx(10 - 20 * 13 / 30)
    assert imp.loc[2, "fg_pct"] == pytest.approx(1 - 10 * 13 / 30)
    assert imp.loc[0, "ft_pct"] == pytest.approx(4 - 5 * 0.8)
    assert imp.loc[2, "a_to"] == pytest.approx(0 - 2 * 9)


def test_availability():
    a = availability(pd.Series([82, 75, 50, 0]), 75, 0.5)
    assert a.tolist() == pytest.approx([1, 1, (50 / 75) ** 0.5, 0])


def test_replacement_lines_by_position(synthetic_players):
    pool = 168
    df = synthetic_players.reset_index(drop=True)
    z, order = pooled_zscores(df, pool, VCFG)
    v = value_players(df, pool, VCFG)
    assert v["in_pool"].sum() == pool
    assert set(order[:pool]) == set(v.index[v["in_pool"]])

    # Hand calc: 5 players eligible at each position, starting from rank pool - 16 (#153).
    below = order[pool - 16:]
    lines = {p: z.loc[[i for i in below if p in df.at[i, "yahoo_positions"].split(",")][:5]].mean()
             for p in "GFC"}
    blended = (lines["G"] + lines["F"] + lines["C"]) / 3
    assert (z - v[CATS]).iloc[0].tolist() == pytest.approx(blended.tolist())
    assert (z - v[CATS]).round(9).drop_duplicates().shape[0] == 1      # same line for everyone


def test_positional_mode_uses_easiest_line(synthetic_players):
    pool = 168
    df = synthetic_players.reset_index(drop=True)
    z, order = pooled_zscores(df, pool, VCFG)
    lines = position_lines(df, z, order, pool, VCFG)
    p = value_players(df, pool, dict(VCFG, replacement_mode="positional"))
    for i in df.index[:40]:
        elig = df.at[i, "yahoo_positions"].split(",")
        best = min((lines[x] for x in elig), key=lambda s: s.sum())
        assert (z.loc[i] - p.loc[i, CATS]).tolist() == pytest.approx(best.tolist())


def test_team_counts_change_replacement(synthetic_players):
    out = value_all(synthetic_players, [12, 13, 14], 14, VCFG)
    for n in (12, 13, 14):
        assert {f"z{n}_{c}" for c in CATS} <= set(out.columns)
        assert out[f"pool{n}"].sum() == n * 14
    # Deeper league -> lower replacement level -> bigger surplus for the same player.
    best = out["value14"].idxmax()
    assert out.loc[best, "value14"] > out.loc[best, "value12"]

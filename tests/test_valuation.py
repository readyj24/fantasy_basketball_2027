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


def test_category_noise_units(synthetic_players):
    from draftboard.valuation import category_noise
    vals = value_all(synthetic_players, [12], 14, VCFG)
    ncfg = {"weekly_games_per_player": 2.8, "team_spread_factor": 0.0,
            "phi": {c: 1.0 for c in ["pts", "reb", "ast", "stl", "blk", "fg3m", "tov", "fg_pct", "ft_pct"]}}
    sig = category_noise(vals, 12, 14, ncfg)
    pool = vals[vals["pool12"]]
    # Counting stat, Poisson (phi=1): sqrt(2 x 14 x mean / G) / sd
    exp = np.sqrt(2 * 14 * pool["stl"].mean() / 2.8) / pool["stl"].std(ddof=0)
    assert sig.loc["stl", "sigma"] == pytest.approx(exp)
    # More games per week -> less noise; opponent spread only adds.
    sig2 = category_noise(vals, 12, 14, dict(ncfg, weekly_games_per_player=5.6))
    assert (sig2["sigma"] < sig["sigma"]).all()
    sig3 = category_noise(vals, 12, 14, dict(ncfg, team_spread_factor=0.7))
    assert (sig3["sigma"] > sig["sigma"]).all()


def test_fit_noise_poisson_and_binomial():
    from scripts.fit_noise import fit
    rng = np.random.default_rng(0)
    rows = []
    for pid in range(40):
        lam, fga = 1 + pid / 20, 10 + pid % 8
        for _ in range(60):
            fgm = rng.binomial(fga, 0.48)
            rows.append({"PLAYER_ID": pid, "MIN": 30, "PTS": rng.poisson(15), "REB": rng.poisson(6),
                         "AST": rng.poisson(4), "STL": rng.poisson(lam), "BLK": rng.poisson(lam),
                         "TOV": rng.poisson(2), "FG3M": rng.poisson(2), "FGM": fgm, "FGA": fga,
                         "FTM": rng.binomial(5, 0.8), "FTA": 5})
    phi = fit(pd.DataFrame(rows))
    assert phi["stl"] == pytest.approx(1.0, abs=0.15)          # Poisson -> 1
    assert phi["fg_pct"] == pytest.approx(1.0, abs=0.2)        # fixed attempts, binomial -> ~1

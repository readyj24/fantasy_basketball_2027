import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def synthetic_players() -> pd.DataFrame:
    """Random but plausible stat lines -- test fixture only, never real data."""
    rng = np.random.default_rng(7)
    n = 260
    tier = np.linspace(1.6, 0.35, n)
    fga = 15 * tier + rng.normal(0, 1, n).clip(-2, 2)
    fta = 5 * tier + rng.uniform(0.3, 1.5, n)
    ast = 5 * tier * rng.uniform(0.4, 1.6, n)
    df = pd.DataFrame({
        "name": [f"Player {i:03d}" for i in range(n)],
        "team": rng.choice(["BOS", "DEN", "LAL", "OKC", "NYK", "MIN"], n),
        "yahoo_positions": rng.choice(["G", "G,F", "F", "F,C", "C"], n),
        "games": rng.integers(45, 80, n).astype(float),
        "mpg": 34 * tier.clip(max=1.1),
        "pts": 20 * tier + rng.normal(0, 1.5, n),
        "reb": 7 * tier * rng.uniform(0.5, 1.6, n),
        "ast": ast,
        "stl": 1.1 * tier * rng.uniform(0.6, 1.4, n),
        "blk": 0.8 * tier * rng.uniform(0.2, 2.0, n),
        "tov": ast * rng.uniform(0.25, 0.55, n) + 0.5,
        "fg3m": 2.0 * tier * rng.uniform(0.1, 1.6, n),
        "fga": fga,
        "fgm": fga * rng.uniform(0.42, 0.58, n),
        "fta": fta,
        "ftm": fta * rng.uniform(0.62, 0.9, n),
    })
    df["adp"] = (np.arange(1, n + 1) + rng.normal(0, 6, n)).clip(1)
    df["yahoo_rank"] = (np.arange(1, n + 1) + rng.normal(0, 8, n)).clip(1)
    return df

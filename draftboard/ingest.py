"""Read raw projection / ADP / Yahoo-rank tables and build data/players.csv.

The raw files can be scraped or pasted. Column names are matched loosely
(case/punctuation-insensitive aliases), so a table copy-pasted from Hashtag
Basketball, FantasyPros or Yahoo usually loads without editing.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from .names import fuzzy_map, load_overrides, normalize_name

PLAYER_COLUMNS = [
    "name", "team", "yahoo_positions", "games", "mpg", "pts", "reb", "ast", "stl",
    "blk", "tov", "fg3m", "fgm", "fga", "ftm", "fta", "adp", "yahoo_rank",
]

_ALIASES = {
    "name": ["player", "name", "playername", "player_name"],
    "team": ["team", "tm", "nbateam"],
    "positions": ["pos", "position", "positions", "yahoopositions", "elig", "eligibility"],
    "games": ["gp", "g", "games", "gamesplayed"],
    "mpg": ["mpg", "min", "minutes", "mp"],
    "pts": ["pts", "points", "pt"],
    "reb": ["reb", "treb", "trb", "rebounds", "rpg"],
    "ast": ["ast", "assists", "apg"],
    "stl": ["stl", "steals", "st", "spg"],
    "blk": ["blk", "blocks", "bpg"],
    "tov": ["to", "tov", "turnovers", "topg"],
    "fg3m": ["3pm", "3ptm", "3pt", "threes", "fg3m", "3p", "tpm"],
    "fgm": ["fgm"],
    "fga": ["fga"],
    "ftm": ["ftm"],
    "fta": ["fta"],
    "fg_pct": ["fg", "fgpct", "fgpercent", "fieldgoal"],
    "ft_pct": ["ft", "ftpct", "ftpercent", "freethrow"],
    "adp": ["adp", "yahoo", "yahooadp", "avg", "average", "avgpick", "averagepick"],
    "rank": ["rank", "rk", "yahoorank", "orank", "ovr", "overall", "r"],
}


def _key(col: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(col).lower().replace("%", "pct")).replace("pct", "")


def _pick(df: pd.DataFrame, field: str, required: bool = True) -> str | None:
    keys = {_key(c): c for c in df.columns}
    for alias in _ALIASES[field]:
        if alias in keys:
            return keys[alias]
    if field == "name":                       # "Player Team (Position)"
        for k, c in keys.items():
            if k.startswith("player"):
                return c
    if required:
        raise KeyError(f"no column for {field!r}; columns are {list(df.columns)}")
    return None


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.replace(",", "").str.strip(), errors="coerce")


_MADE_ATT = re.compile(r"\(\s*([\d.]+)\s*/\s*([\d.]+)\s*\)")


def _made_attempts(df: pd.DataFrame, pct_field: str, made: str, att: str) -> tuple[pd.Series, pd.Series]:
    """FGM/FGA from explicit columns, or Hashtag's '0.493 (7.8/15.8)' cells."""
    m_col, a_col = _pick(df, made, False), _pick(df, att, False)
    if m_col and a_col:
        return _num(df[m_col]), _num(df[a_col])
    p_col = _pick(df, pct_field, False)
    if p_col:
        parsed = df[p_col].astype(str).str.extract(_MADE_ATT)
        if parsed.notna().all(axis=None):
            return pd.to_numeric(parsed[0]), pd.to_numeric(parsed[1])
    raise KeyError(
        f"need {made}/{att} columns or '{pct_field}' cells like '0.493 (7.8/15.8)'; "
        f"columns are {list(df.columns)}"
    )


def to_gfc(positions: str) -> str:
    """'PG,SG' -> 'G'; 'SF,PF,C' -> 'F,C'. Already-G/F/C strings pass through."""
    out = []
    for p in re.split(r"[^A-Za-z]+", str(positions).upper()):
        if p in ("PG", "SG", "G"):
            out.append("G")
        elif p in ("SF", "PF", "F"):
            out.append("F")
        elif p == "C":
            out.append("C")
    return ",".join(x for x in "GFC" if x in out)


def read_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path)
    text = path.read_text(encoding="utf-8-sig")
    sep = "\t" if text.count("\t") > text.count(",") else ","
    df = pd.read_csv(path, sep=sep, encoding="utf-8-sig")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def load_projections(path: str | Path) -> pd.DataFrame:
    raw = read_table(path)
    name_col = _pick(raw, "name")
    raw = raw[raw[name_col].notna()]
    # Pasted Hashtag tables repeat the header row every 10-20 players.
    raw = raw[raw[name_col].astype(str).str.upper() != "PLAYER"].reset_index(drop=True)
    fgm, fga = _made_attempts(raw, "fg_pct", "fgm", "fga")
    ftm, fta = _made_attempts(raw, "ft_pct", "ftm", "fta")
    out = pd.DataFrame({
        "name": raw[name_col].astype(str).str.strip(),
        "team": raw[_pick(raw, "team")].astype(str).str.strip() if _pick(raw, "team", False) else "",
        "yahoo_positions": raw[_pick(raw, "positions")].map(to_gfc) if _pick(raw, "positions", False) else "",
        "games": _num(raw[_pick(raw, "games")]),
        "mpg": _num(raw[_pick(raw, "mpg")]) if _pick(raw, "mpg", False) else np.nan,
        "pts": _num(raw[_pick(raw, "pts")]),
        "reb": _num(raw[_pick(raw, "reb")]),
        "ast": _num(raw[_pick(raw, "ast")]),
        "stl": _num(raw[_pick(raw, "stl")]),
        "blk": _num(raw[_pick(raw, "blk")]),
        "tov": _num(raw[_pick(raw, "tov")]),
        "fg3m": _num(raw[_pick(raw, "fg3m")]),
        "fgm": fgm, "fga": fga, "ftm": ftm, "fta": fta,
    })
    bad = out[["games", "pts", "reb", "ast", "tov", "fga"]].isna().any(axis=1)
    if bad.any():
        print(f"  dropping {bad.sum()} projection rows with missing numbers: "
              f"{out.loc[bad, 'name'].head(8).tolist()}")
    return out[~bad].reset_index(drop=True)


def average_projections(a: pd.DataFrame, b: pd.DataFrame, min_accept: float) -> pd.DataFrame:
    """Average numeric projections of a second source into the first."""
    mapping, report = fuzzy_map(b["name"].tolist(), a["name"].tolist(), min_accept)
    report.print_low(95)
    b = b.assign(name=b["name"].map(mapping)).dropna(subset=["name"]).set_index("name")
    a = a.set_index("name")
    num = ["games", "mpg", "pts", "reb", "ast", "stl", "blk", "tov", "fg3m", "fgm", "fga", "ftm", "fta"]
    both = a.index.intersection(b.index)
    a.loc[both, num] = (a.loc[both, num] + b.loc[both, num]) / 2
    return a.reset_index()


def load_ranking(path: str | Path, field: str) -> pd.DataFrame:
    """name + value table for ADP ('adp') or Yahoo default rank ('rank').

    For Yahoo rank, a file with only player names is read as the draft-room
    order (row 1 = rank 1).
    """
    raw = read_table(path)
    name_col = _pick(raw, "name")
    raw = raw[raw[name_col].notna()].reset_index(drop=True)
    col = _pick(raw, field, required=False)
    if col is None and field == "rank":
        value = pd.Series(np.arange(1, len(raw) + 1), dtype=float)
    elif col is None:
        raise KeyError(f"no ADP column in {path}; columns are {list(raw.columns)}")
    else:
        value = _num(raw[col])
    out = pd.DataFrame({"name": raw[name_col].astype(str).str.strip(), "value": value})
    pos_col = _pick(raw, "positions", required=False)
    if pos_col:
        out["positions"] = raw[pos_col].map(to_gfc)
    else:
        # FantasyPros / Yahoo pastes: "Nikola Jokic (DEN - C)" or "Nikola Jokic DEN - C"
        m = raw[name_col].astype(str).str.extract(r"-\s*([A-Z,/]+)\)?\s*$")[0]
        if m.notna().mean() > 0.5:
            out["positions"] = m.map(to_gfc)
    return out.dropna(subset=["value"])


def build_players(cfg: dict, base: Path) -> pd.DataFrame:
    paths = cfg["paths"]
    mcfg = cfg["matching"]
    overrides = load_overrides(base / mcfg["overrides_file"]) if mcfg.get("overrides_file") else {}

    print(f"Projections: {paths['projections']}")
    proj = load_projections(base / paths["projections"])
    if paths.get("projections_secondary"):
        print(f"Averaging in: {paths['projections_secondary']}")
        proj = average_projections(proj, load_projections(base / paths["projections_secondary"]),
                                   mcfg["min_accept"])
    print(f"  {len(proj)} players")

    for field, key, out_col in (("adp", "adp", "adp"), ("rank", "yahoo_rank", "yahoo_rank")):
        src = paths.get(key)
        if not src or not (base / src).exists():
            print(f"{key}: {src} not found -> every player gets {cfg['valuation']['missing_adp']}")
            proj[out_col] = np.nan
            continue
        tbl = load_ranking(base / src, field)
        print(f"{key}: {src} ({len(tbl)} rows)")
        mapping, report = fuzzy_map(tbl["name"].tolist(), proj["name"].tolist(),
                                    mcfg["min_accept"], overrides)
        report.print_low(mcfg["report_below"])
        tbl["proj_name"] = tbl["name"].map(mapping)
        tbl = tbl.dropna(subset=["proj_name"]).drop_duplicates("proj_name")
        proj[out_col] = proj["name"].map(dict(zip(tbl["proj_name"], tbl["value"])))
        if "positions" in tbl:
            # Yahoo's own eligibility beats the projection site's when available.
            yp = proj["name"].map(dict(zip(tbl["proj_name"], tbl["positions"])))
            if key == "yahoo_rank" or (proj["yahoo_positions"] == "").all():
                proj["yahoo_positions"] = yp.where(yp.notna() & (yp != ""), proj["yahoo_positions"])

    # One signal missing for a player -> use the other; both missing -> missing_adp.
    missing = cfg["valuation"]["missing_adp"]
    adp, yr = proj["adp"].copy(), proj["yahoo_rank"].copy()
    proj["adp"] = adp.fillna(yr).fillna(missing)
    proj["yahoo_rank"] = yr.fillna(adp).fillna(missing)
    return proj[PLAYER_COLUMNS]


def dedupe_names(df: pd.DataFrame) -> pd.DataFrame:
    """Two players with the same display name would break the Log dropdown lookup."""
    dup = df["name"].duplicated(keep=False)
    if dup.any():
        df = df.copy()
        df.loc[dup, "name"] = df.loc[dup, "name"] + " (" + df.loc[dup, "team"].astype(str) + ")"
    return df


__all__ = ["build_players", "load_projections", "load_ranking", "to_gfc", "normalize_name",
           "dedupe_names"]

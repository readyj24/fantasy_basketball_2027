"""Parse a copy-paste of the Yahoo draft-room player list.

Each player block looks like:

    N. Jokić            <- name (repeated)
    N. Jokić
    Q                   <- optional status (Q, O, P, NA, GTD, INJ ...)
    C                   <- position eligibility
    DEN                 <- team
    1.3  1  1.3  71  .574 ...   <- XRank, Rank, L7ADP, GP, FG%, FT%, 3PTM, PTS, REB, AST, ST, BLK, A/T

"Your Turn - Nth Pick" separators are ignored. Names are abbreviated, so
matching to projections uses first initial + last name + team.
"""
from __future__ import annotations

import re

import pandas as pd

from .names import normalize_name

# Yahoo team codes -> Hashtag's
TEAM_MAP = {"GSW": "GS", "NOP": "NO", "NYK": "NY", "PHX": "PHO", "SAS": "SA"}
STAT_COLS = ["xrank", "rank", "l7adp", "gp", "fg_pct", "ft_pct", "fg3m", "pts", "reb", "ast",
             "stl", "blk", "a_to"]
_POS = re.compile(r"^[GFC](,[GFC])*$")


def _num(x: str) -> float | None:
    x = x.strip()
    return None if x in ("", "-") else float(x)


def parse_board(text: str) -> pd.DataFrame:
    lines = [ln.rstrip() for ln in text.splitlines()]
    rows = []
    block: list[str] = []
    for ln in lines + [""]:
        if ln.startswith("Queue") or ln.startswith("Your Turn"):
            continue
        if ln.strip():
            block.append(ln.strip())
            continue
        if not block:
            continue
        nums = block[-1].split("\t")
        if len(nums) >= len(STAT_COLS) and len(block) >= 4:
            team = block[-2]
            pos = block[-3]
            status = block[-4] if len(block) >= 5 and not _POS.match(block[-4]) and block[-4] != block[0] else ""
            if not _POS.match(pos):
                raise ValueError(f"unexpected block: {block}")
            rec = {"yahoo_name": block[0], "status": status, "positions": pos,
                   "team": TEAM_MAP.get(team, team)}
            rec.update({c: _num(v) for c, v in zip(STAT_COLS, nums)})
            rows.append(rec)
        block = []
    df = pd.DataFrame(rows)
    df["room_order"] = range(1, len(df) + 1)
    return df


def _key(name: str) -> tuple[str, str]:
    """(first initial, last token): 'K. Towns' and 'Karl-Anthony Towns' -> ('k', 'towns')."""
    parts = normalize_name(name).split()
    return (parts[0][0] if parts else "", parts[-1] if len(parts) > 1 else "")


def match_to_projections(board: pd.DataFrame, proj: pd.DataFrame) -> pd.Series:
    """Full projection name for each board row (None if no match).

    Same initial + last name, same team first, then any team. Ties (Jalen vs. Jaylin
    Williams, both OKC) go to the player listed first in the projections, i.e. the
    higher-ranked one.
    """
    keyed = [(n, t, _key(n)) for n, t in zip(proj["name"], proj["team"])]
    out, used = [], set()
    for yname, team in zip(board["yahoo_name"], board["team"]):
        k = _key(yname)
        hit = None
        for same_team in (True, False):
            cands = [n for n, t, kk in keyed if kk == k and n not in used and (t == team or not same_team)]
            if cands:
                hit = cands[0]
                break
        if hit:
            used.add(hit)
        out.append(hit)
    return pd.Series(out, index=board.index)

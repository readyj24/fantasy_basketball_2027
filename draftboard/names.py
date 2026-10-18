"""Player-name normalization and fuzzy joining."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def normalize_name(name: str) -> str:
    """'Luka Dončić' -> 'luka doncic', 'Jaren Jackson Jr.' -> 'jaren jackson'."""
    if not isinstance(name, str):
        return ""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().replace("&#39;", "'")
    s = re.sub(r"\(.*?\)", " ", s)            # "Nikola Jokic (DEN - C)"
    s = re.sub(r"[.'`’]", "", s)               # O'Neale -> oneale, P.J. -> pj
    s = re.sub(r"[^a-z0-9 ]+", " ", s)         # hyphens, commas
    # Drop Jr./III etc. but never the first token ("V. Wembanyama" is not a suffix).
    parts = s.split()
    parts = parts[:1] + [p for p in parts[1:] if p not in _SUFFIXES]
    return " ".join(parts)


@dataclass
class MatchReport:
    rows: list[tuple[str, str | None, float]]

    def print_low(self, below: float) -> None:
        low = [r for r in self.rows if r[2] < below]
        if not low:
            return
        print(f"\n  {len(low)} name matches under {below}:")
        for left, right, score in sorted(low, key=lambda r: r[2]):
            arrow = right if right is not None else "(no match)"
            print(f"    {score:5.1f}  {left!r:32} -> {arrow!r}")


def load_overrides(path: str | Path | None) -> dict[str, str]:
    """CSV with columns `source_name,projection_name` for manual fixes."""
    if not path or not Path(path).exists():
        return {}
    df = pd.read_csv(path)
    return {normalize_name(a): normalize_name(b) for a, b in zip(df.iloc[:, 0], df.iloc[:, 1])}


def fuzzy_map(
    source_names: list[str],
    target_names: list[str],
    min_accept: float,
    overrides: dict[str, str] | None = None,
) -> tuple[dict[str, str], MatchReport]:
    """Map each source name to a target name (both raw strings).

    Exact normalized matches win; otherwise best token-sort ratio. Each target
    is used at most once so two sources can't both claim the same player.
    """
    overrides = overrides or {}
    norm_targets: dict[str, str] = {}
    for t in target_names:
        norm_targets.setdefault(normalize_name(t), t)
    choices = list(norm_targets)

    mapping: dict[str, str] = {}
    report: list[tuple[str, str | None, float]] = []
    taken: set[str] = set()
    pending: list[str] = []

    for s in source_names:
        n = overrides.get(normalize_name(s), normalize_name(s))
        if n in norm_targets and n not in taken:
            mapping[s] = norm_targets[n]
            taken.add(n)
        else:
            pending.append(s)

    for s in pending:
        n = overrides.get(normalize_name(s), normalize_name(s))
        free = [c for c in choices if c not in taken]
        hit = process.extractOne(n, free, scorer=fuzz.token_sort_ratio) if free else None
        if hit and hit[1] >= min_accept:
            mapping[s] = norm_targets[hit[0]]
            taken.add(hit[0])
            report.append((s, norm_targets[hit[0]], float(hit[1])))
        else:
            report.append((s, norm_targets[hit[0]] if hit else None, float(hit[1]) if hit else 0.0))
    return mapping, MatchReport(report)

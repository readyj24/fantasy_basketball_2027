"""Backend-neutral spreadsheet model rendered by gsheet.py (API) or xlsx.py (file)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


def col_letter(idx: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    s = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        s = chr(65 + rem) + s
    return s


def col_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def a1(row: int, col: int, absolute: bool = False) -> str:
    """0-based (row, col) -> 'B3' (or '$B$3')."""
    d = "$" if absolute else ""
    return f"{d}{col_letter(col)}{d}{row + 1}"


_A1 = re.compile(r"^\$?([A-Z]+)\$?(\d+)(?::\$?([A-Z]+)\$?(\d+))?$")


def parse_range(rng: str) -> tuple[int, int, int, int]:
    """'B3:D9' -> (r0, c0, r1, c1) 0-based inclusive."""
    m = _A1.match(rng)
    if not m:
        raise ValueError(rng)
    c0, r0 = col_index(m.group(1)), int(m.group(2)) - 1
    if m.group(3):
        c1, r1 = col_index(m.group(3)), int(m.group(4)) - 1
    else:
        c1, r1 = c0, r0
    return r0, c0, r1, c1


@dataclass
class Fmt:
    number: str | None = None      # e.g. '0.00', '0%'
    bold: bool = False
    italic: bool = False
    size: int | None = None
    bg: str | None = None          # '#RRGGBB'
    fg: str | None = None
    align: str | None = None       # LEFT / CENTER / RIGHT
    wrap: bool = False


@dataclass
class Validation:
    rng: str
    kind: str                      # 'range' | 'list' | 'checkbox'
    source: str | list[Any] | None = None
    strict: bool = True


@dataclass
class CondFormat:
    rng: str
    kind: str                      # 'formula' | 'scale'
    formula: str | None = None
    bg: str | None = None
    fg: str | None = None
    bold: bool = False
    strike: bool = False
    # color scale
    min_color: str = "#E67C73"
    mid_color: str = "#FFFFFF"
    max_color: str = "#57BB8A"
    mid_value: float = 0.0


@dataclass
class Sheet:
    name: str
    cells: dict[tuple[int, int], Any] = field(default_factory=dict)
    widths: dict[int, int] = field(default_factory=dict)
    hidden_cols: list[int] = field(default_factory=list)
    frozen_rows: int = 0
    frozen_cols: int = 0
    formats: list[tuple[str, Fmt]] = field(default_factory=list)
    merges: list[str] = field(default_factory=list)
    validations: list[Validation] = field(default_factory=list)
    cond_formats: list[CondFormat] = field(default_factory=list)
    tab_color: str | None = None

    def set(self, ref: str, value: Any) -> None:
        r, c, _, _ = parse_range(ref)
        self.cells[(r, c)] = value

    def put(self, row: int, col: int, value: Any) -> None:
        self.cells[(row, col)] = value

    def put_row(self, row: int, col: int, values: list[Any]) -> None:
        for i, v in enumerate(values):
            self.cells[(row, col + i)] = v

    def fmt(self, rng: str, **kw: Any) -> None:
        self.formats.append((rng, Fmt(**kw)))

    @property
    def n_rows(self) -> int:
        return max((r for r, _ in self.cells), default=0) + 1

    @property
    def n_cols(self) -> int:
        return max((c for _, c in self.cells), default=0) + 1

    def grid(self) -> list[list[Any]]:
        g = [["" for _ in range(self.n_cols)] for _ in range(self.n_rows)]
        for (r, c), v in self.cells.items():
            g[r][c] = v
        return g


@dataclass
class Workbook:
    sheets: list[Sheet] = field(default_factory=list)
    named: dict[str, tuple[str, str]] = field(default_factory=dict)   # name -> (sheet, 'B2')

    def add(self, name: str) -> Sheet:
        s = Sheet(name)
        self.sheets.append(s)
        return s

    def sheet(self, name: str) -> Sheet:
        return next(s for s in self.sheets if s.name == name)

"""Parse a saved Hashtag Basketball projections page (the full .html) into CSVs."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

TABLE_ID = "ContentPlaceHolder1_GridView1"


def parse_html(path: str | Path) -> pd.DataFrame:
    soup = BeautifulSoup(Path(path).read_text(encoding="utf-8", errors="replace"), "lxml")
    table = soup.find("table", id=TABLE_ID)
    if table is None:
        raise ValueError(f"{path}: no projections table ({TABLE_ID})")
    rows = table.find_all("tr")
    header = [c.get_text(" ", strip=True) for c in rows[0].find_all(["th", "td"])]
    out = []
    for tr in rows[1:]:
        tds = tr.find_all("td")
        if len(tds) != len(header):
            continue                                   # repeated header rows use <th>
        cells = [td.get_text(" ", strip=True) for td in tds]
        # Name cell holds the full name link plus a short "N.Jokic" link for mobile.
        full = tds[header.index("PLAYER")].find("a", class_="d-sm-inline")
        cells[header.index("PLAYER")] = full.get_text(strip=True) if full else cells[header.index("PLAYER")]
        out.append(cells)
    df = pd.DataFrame(out, columns=header)
    return df[df["PLAYER"].str.upper() != "PLAYER"].reset_index(drop=True)


def selected_options(path: str | Path) -> dict[str, str]:
    soup = BeautifulSoup(Path(path).read_text(encoding="utf-8", errors="replace"), "lxml")
    res = {}
    for s in soup.find_all("select"):
        opt = s.find("option", selected=True)
        if opt and s.get("id"):
            res[s["id"].replace("ContentPlaceHolder1_", "")] = opt.get_text(strip=True)
    return res

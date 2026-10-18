"""Render a Workbook model to a Google Sheet via gspread (service account).

Idempotent: every run deletes the managed tabs and named ranges and rebuilds
them, so rerunning never leaves stale formulas behind.
"""
from __future__ import annotations

import time
from typing import Any

import gspread
from gspread.utils import ValueInputOption

from .model import CondFormat, Fmt, Sheet, Validation, Workbook, parse_range


def _rgb(hex_color: str) -> dict[str, float]:
    h = hex_color.lstrip("#")
    return {k: int(h[i:i + 2], 16) / 255 for k, i in (("red", 0), ("green", 2), ("blue", 4))}


def _grid(sheet_id: int, rng: str) -> dict[str, int]:
    r0, c0, r1, c1 = parse_range(rng)
    return {"sheetId": sheet_id, "startRowIndex": r0, "endRowIndex": r1 + 1,
            "startColumnIndex": c0, "endColumnIndex": c1 + 1}


def open_spreadsheet(cfg: dict, base) -> gspread.Spreadsheet:
    g = cfg["gsheets"]
    gc = gspread.service_account(filename=str(base / g["service_account_json"]),
                                 http_client=gspread.BackOffHTTPClient)
    if g.get("spreadsheet_id"):
        return gc.open_by_key(g["spreadsheet_id"])
    return gc.open(g["spreadsheet_title"])


def _fmt_request(sid: int, rng: str, f: Fmt) -> dict[str, Any]:
    cell: dict[str, Any] = {}
    fields = []
    if f.number:
        pattern_type = "PERCENT" if "%" in f.number else "NUMBER"
        cell["numberFormat"] = {"type": pattern_type, "pattern": f.number}
        fields.append("userEnteredFormat.numberFormat")
    tf: dict[str, Any] = {}
    if f.bold:
        tf["bold"] = True
    if f.italic:
        tf["italic"] = True
    if f.size:
        tf["fontSize"] = f.size
    if f.fg:
        tf["foregroundColor"] = _rgb(f.fg)
    if tf:
        cell["textFormat"] = tf
        fields += [f"userEnteredFormat.textFormat.{k}" for k in tf]
    if f.bg:
        cell["backgroundColor"] = _rgb(f.bg)
        fields.append("userEnteredFormat.backgroundColor")
    if f.align:
        cell["horizontalAlignment"] = f.align
        fields.append("userEnteredFormat.horizontalAlignment")
    if f.wrap:
        cell["wrapStrategy"] = "WRAP"
        fields.append("userEnteredFormat.wrapStrategy")
    return {"repeatCell": {"range": _grid(sid, rng), "cell": {"userEnteredFormat": cell},
                           "fields": ",".join(fields)}}


def _validation_request(sid: int, v: Validation) -> dict[str, Any]:
    if v.kind == "checkbox":
        cond = {"type": "BOOLEAN"}
    elif v.kind == "list":
        cond = {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": str(x)} for x in v.source]}
    else:
        cond = {"type": "ONE_OF_RANGE", "values": [{"userEnteredValue": v.source}]}
    return {"setDataValidation": {"range": _grid(sid, v.rng), "rule": {
        "condition": cond, "strict": v.strict, "showCustomUi": v.kind != "checkbox"}}}


def _cf_request(sid: int, cf: CondFormat, index: int) -> dict[str, Any]:
    if cf.kind == "scale":
        rule = {"ranges": [_grid(sid, cf.rng)], "gradientRule": {
            "minpoint": {"color": _rgb(cf.min_color), "type": "MIN"},
            "midpoint": {"color": _rgb(cf.mid_color), "type": "NUMBER", "value": str(cf.mid_value)},
            "maxpoint": {"color": _rgb(cf.max_color), "type": "MAX"}}}
    else:
        fmt: dict[str, Any] = {}
        tf: dict[str, Any] = {}
        if cf.bg:
            fmt["backgroundColor"] = _rgb(cf.bg)
        if cf.fg:
            tf["foregroundColor"] = _rgb(cf.fg)
        if cf.bold:
            tf["bold"] = True
        if cf.strike:
            tf["strikethrough"] = True
        if tf:
            fmt["textFormat"] = tf
        rule = {"ranges": [_grid(sid, cf.rng)], "booleanRule": {
            "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": cf.formula}]},
            "format": fmt}}
    return {"addConditionalFormatRule": {"rule": rule, "index": index}}


def _sheet_requests(sid: int, s: Sheet) -> list[dict[str, Any]]:
    reqs: list[dict[str, Any]] = []
    props: dict[str, Any] = {"sheetId": sid, "gridProperties": {
        "frozenRowCount": s.frozen_rows, "frozenColumnCount": s.frozen_cols}}
    fields = "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"
    if s.tab_color:
        props["tabColorStyle"] = {"rgbColor": _rgb(s.tab_color)}
        fields += ",tabColorStyle"
    reqs.append({"updateSheetProperties": {"properties": props, "fields": fields}})
    for col, px in s.widths.items():
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": col, "endIndex": col + 1},
            "properties": {"pixelSize": px}, "fields": "pixelSize"}})
    for col in s.hidden_cols:
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": col, "endIndex": col + 1},
            "properties": {"hiddenByUser": True}, "fields": "hiddenByUser"}})
    for rng in s.merges:
        reqs.append({"mergeCells": {"range": _grid(sid, rng), "mergeType": "MERGE_ALL"}})
    for rng, f in s.formats:
        reqs.append(_fmt_request(sid, rng, f))
    for v in s.validations:
        reqs.append(_validation_request(sid, v))
    for i, cf in enumerate(s.cond_formats):
        reqs.append(_cf_request(sid, cf, i))
    return reqs


def render(wb: Workbook, ss: gspread.Spreadsheet) -> None:
    meta = ss.fetch_sheet_metadata()
    # 1. Clear named ranges and old tabs (keep a scratch tab so the file is never empty).
    reqs: list[dict[str, Any]] = [{"deleteNamedRange": {"namedRangeId": nr["namedRangeId"]}}
                                  for nr in meta.get("namedRanges", [])]
    scratch = "__rebuild__"
    existing = {sh["properties"]["title"]: sh["properties"]["sheetId"] for sh in meta["sheets"]}
    if scratch not in existing:
        reqs.append({"addSheet": {"properties": {"title": scratch}}})
    ss.batch_update({"requests": reqs})
    reqs = [{"deleteSheet": {"sheetId": sid}} for t, sid in existing.items() if t != scratch]
    for i, s in enumerate(wb.sheets):
        reqs.append({"addSheet": {"properties": {
            "title": s.name, "index": i,
            "gridProperties": {"rowCount": max(s.n_rows + 5, 50), "columnCount": max(s.n_cols + 2, 26)}}}})
    ss.batch_update({"requests": reqs})
    meta = ss.fetch_sheet_metadata()
    ids = {sh["properties"]["title"]: sh["properties"]["sheetId"] for sh in meta["sheets"]}

    # 2. Named ranges first so formulas resolve as soon as they land.
    reqs = []
    for name, (sheet, rng) in wb.named.items():
        reqs.append({"addNamedRange": {"namedRange": {
            "name": name, "range": _grid(ids[sheet], rng.replace("$", ""))}}})
    reqs.append({"deleteSheet": {"sheetId": ids[scratch]}})
    ss.batch_update({"requests": reqs})

    # 3. Values and formulas (USER_ENTERED so formulas evaluate).
    data = [{"range": f"'{s.name}'!A1", "values": s.grid()} for s in wb.sheets]
    ss.values_batch_update({"valueInputOption": ValueInputOption.user_entered, "data": data})

    # 4. Formatting, validation, conditional formatting.
    reqs = []
    for s in wb.sheets:
        reqs += _sheet_requests(ids[s.name], s)
    for i in range(0, len(reqs), 400):
        ss.batch_update({"requests": reqs[i:i + 400]})
        time.sleep(0.5)

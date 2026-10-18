"""Part 4: run fake full drafts through the live Google Sheet and check the board.

For each (NumTeams, MySlot) scenario: opponents pick by noisy opp_rank, I pick
the Board's top Score, and at each of my turns the script reads the Sheet back
and asserts the invariants from the spec. Finishes by clearing the Log and
restoring Config, so the Sheet is ready for the real draft.
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gspread.utils import ValueRenderOption  # noqa: E402

from draftboard import ROOT, load_config  # noqa: E402
from draftboard.gsheet import open_spreadsheet  # noqa: E402

UNF = ValueRenderOption.unformatted
FAILS: list[str] = []


def check(ok: bool, msg: str) -> None:
    if not ok:
        FAILS.append(msg)
        print(f"    FAIL: {msg}")


def snake_slot(pick: int, n: int) -> int:
    rnd = -(-pick // n)
    return (pick - 1) % n + 1 if rnd % 2 else n - (pick - 1) % n


class Board:
    def __init__(self, ss, max_picks: int):
        self.ss = ss
        self.max_picks = max_picks
        self.cfg_ws = ss.worksheet("Config")
        self.log_ws = ss.worksheet("Log")
        self.board_ws = ss.worksheet("Board")
        self.pl_ws = ss.worksheet("Players")
        self.my_ws = ss.worksheet("My Team")

    def named(self, *names: str) -> dict[str, object]:
        res = self.ss.values_batch_get(list(names), params={"valueRenderOption": UNF})
        out = {}
        for name, vr in zip(names, res["valueRanges"]):
            vals = vr.get("values", [[None]])
            out[name] = vals[0][0] if vals and vals[0] else None
        return out

    def set_config(self, **kw) -> None:
        self.ss.values_batch_update({"valueInputOption": "USER_ENTERED", "data": [
            {"range": k, "values": [[v]]} for k, v in kw.items()]})

    mode = "log"                                   # "log" = type into Log, "tab" = Draft checkboxes

    def draft_rows(self) -> dict[str, int]:
        if not hasattr(self, "_drows"):
            names = self.ss.worksheet("Draft").get("C3:C", value_render_option=UNF)
            self._drows = {r[0]: i + 3 for i, r in enumerate(names) if r}
        return self._drows

    def clear_log(self) -> None:
        self.log_ws.batch_clear([f"D2:D{self.max_picks + 1}"])
        n = len(self.draft_rows())
        self.ss.worksheet("Draft").update([[False, False]] * n, f"A3:B{n + 2}",
                                          value_input_option="USER_ENTERED")

    def write_picks(self, start_pick: int, names: list[str], mine: bool = False) -> None:
        if not names:
            return
        if self.mode == "tab":
            col = "B" if mine else "A"
            rows = self.draft_rows()
            self.ss.values_batch_update({"valueInputOption": "USER_ENTERED", "data": [
                {"range": f"Draft!{col}{rows[n]}", "values": [[True]]} for n in names]})
            return
        rng = f"D{start_pick + 1}:D{start_pick + len(names)}"
        self.log_ws.update([[n] for n in names], rng, value_input_option="USER_ENTERED")

    def players(self) -> list[dict]:
        rows = self.pl_ws.get("A1:Z", value_render_option=UNF)
        hdr = rows[0]
        return [dict(zip(hdr, r + [""] * (len(hdr) - len(r)))) for r in rows[1:] if r and r[0]]

    def state(self) -> dict:
        res = self.ss.values_batch_get(["Board!A1:L3", "Board!A6:Q45", "Board!S6:Y15"],
                                       params={"valueRenderOption": UNF})["valueRanges"]
        hdr, table, sanity = (vr.get("values", []) for vr in res)
        labels = hdr[1]
        vals = hdr[2] + [""] * (len(labels) - len(hdr[2]))
        st = dict(zip(labels, vals))
        st["banner"] = hdr[0][0] if hdr and hdr[0] else ""
        st["table"] = [r for r in table if r and r[0]]
        st["sanity"] = [r for r in sanity if r and r[0]]
        return st


def run_scenario(b: Board, n: int, slot: int, rounds: int, seed: int, mode: str = "log") -> dict[str, float]:
    b.mode = mode
    print(f"\n=== {n} teams, my slot {slot}, picks via {'Draft tab checkboxes' if mode == 'tab' else 'Log'} ===")
    b.clear_log()
    b.set_config(NumTeams=n, MySlot=slot)
    time.sleep(2)
    total = n * rounds
    st = b.named("TotalPicks", "CurrentPick", "MyNextPick")
    check(st["TotalPicks"] == total, f"TotalPicks {st['TotalPicks']} != {total}")
    check(st["CurrentPick"] == 1, f"CurrentPick {st['CurrentPick']} != 1 on empty log")
    my_picks = [p for p in range(1, total + 1) if snake_slot(p, n) == slot]
    check(st["MyNextPick"] == my_picks[0], f"MyNextPick {st['MyNextPick']} != {my_picks[0]}")

    log = b.log_ws.get(f"A2:C{b.max_picks + 1}", value_render_option=UNF)
    bad = [(int(r[0]), r[2]) for r in log if int(r[0]) <= total and r[2] != snake_slot(int(r[0]), n)]
    check(not bad, f"snake column wrong at {bad[:5]}")
    for p in (n, n + 1, 2 * n, 2 * n + 1):
        print(f"    pick {p:3d} -> team {log[p - 1][2]}")

    players = b.players()
    opp_rank = {p["Name"]: float(p["Opp rank"]) for p in players}
    value = {p["Name"]: float(p["Value"]) for p in players}
    rng = random.Random(seed)
    drafted: list[str] = []
    pending: list[str] = []
    mine: list[str] = []
    checked_between = False

    pick = 1
    while pick <= total:
        if snake_slot(pick, n) == slot:
            b.write_picks(pick - len(pending), pending)
            pending = []
            st = b.state()
            names = [r[0] for r in st["table"]]
            check(st["banner"].startswith("ON THE CLOCK"), f"pick {pick}: banner {st['banner']!r}")
            check(st["Current pick"] == pick, f"pick {pick}: CurrentPick {st['Current pick']}")
            check(st["My next pick"] == pick, f"pick {pick}: MyNextPick {st['My next pick']}")
            following = next((p for p in my_picks if p > pick), total + 1)
            check(st["Target pick"] == following, f"pick {pick}: TargetPick {st['Target pick']} != {following}")
            leaked = set(names) & set(drafted)
            check(not leaked, f"pick {pick}: drafted players on Board {sorted(leaked)[:5]}")
            check(len(names) == min(40, len(opp_rank) - len(drafted)), f"pick {pick}: table has {len(names)} rows")
            scores = [r[3] for r in st["table"]]
            bad = [(names[i], scores[i], names[i + 1], scores[i + 1]) for i in range(len(scores) - 1)
                   if not scores[i] >= scores[i + 1] - 1e-9]
            check(not bad, f"pick {pick}: Board not sorted by Score: {bad[:3]}")
            sv = [r[2] for r in st["sanity"]]
            check(sv == sorted(sv, reverse=True) and not set(r[0] for r in st["sanity"]) & set(drafted),
                  f"pick {pick}: sanity table wrong")
            choice = names[0]
            print(f"    pick {pick:3d} (rd {st['Round']}): {choice:26} Value {value[choice]:5.2f}  "
                  f"Score {st['table'][0][3]:5.2f}  Fit {st['table'][0][4]:5.2f}  PAvail {st['table'][0][6]:.0%}  "
                  f"opp picks until next {st['Opp picks until']}  Drift {st['Drift']:+.1f}")
            b.write_picks(pick, [choice], mine=True)
            drafted.append(choice)
            mine.append(choice)
        else:
            taken = set(drafted)
            avail = [p for p in opp_rank if p not in taken]
            choice = min(avail, key=lambda p: opp_rank[p] + rng.gauss(0, max(2, 0.18 * opp_rank[p])))
            drafted.append(choice)
            pending.append(choice)
            nxt = next((p for p in my_picks if p > pick), None)
            if not checked_between and nxt and nxt - pick >= 3 and pick > slot:
                b.write_picks(pick - len(pending) + 1, pending)
                pending = []
                st = b.state()
                check(st["banner"].startswith(f"{nxt - pick - 1} picks until you"),
                      f"pick {pick}: off-clock banner {st['banner']!r}")
                check(st["Target pick"] == nxt == st["My next pick"],
                      f"pick {pick}: off-clock TargetPick {st['Target pick']} MyNext {st['My next pick']} != {nxt}")
                check(st["Opp picks until"] == nxt - pick - 1, f"pick {pick}: PicksUntil {st['Opp picks until']}")
                checked_between = True
        pick += 1
    b.write_picks(total - len(pending) + 1, pending)

    st = b.state()
    check(st["banner"] == "DRAFT COMPLETE", f"end: banner {st['banner']!r}")
    check(st["Current pick"] == total + 1, f"end: CurrentPick {st['Current pick']}")
    check(not set(r[0] for r in st["table"]) & set(drafted), "end: drafted player on Board")
    pl = b.players()
    n_drafted = sum(1 for p in pl if p["Drafted"] is True)
    check(n_drafted == total, f"end: {n_drafted} players marked drafted, expected {total}")

    # Grayed-out extra Log rows are ignored.
    if total < b.max_picks and mode == "log":
        leftover = next(p for p in opp_rank if p not in set(drafted))
        b.write_picks(total + 1, [leftover])
        st2 = b.named("CurrentPick")
        dr = next(p for p in b.players() if p["Name"] == leftover)["Drafted"]
        check(st2["CurrentPick"] == total + 1 and dr is False,
              f"extra row {total + 1} counted (CurrentPick {st2['CurrentPick']}, drafted {dr})")
        b.log_ws.batch_clear([f"D{total + 2}"])

    team = b.my_ws.get("A4:A17", value_render_option=UNF)
    got = [r[0] for r in team if r and r[0]]
    check(sorted(got) == sorted(mine), f"My Team shows {sorted(got)[:3]}... expected {sorted(mine)[:3]}...")
    status = b.my_ws.get("A1:B60", value_render_option=UNF)
    for r in status:
        if r and r[0] in ("Status", "Picks left"):
            print(f"    My Team {r[0]}: {r[1] if len(r) > 1 else ''}")
            if r[0] == "Status":
                check(not str(r[1]).startswith("⚠ CAN"), f"roster can't fill starting slots: {r[1]}")
    print(f"    my team: {', '.join(mine)}")
    return value


def punt_test(b: Board, cat_row: int) -> None:
    print("\n=== punt toggle ===")
    b.clear_log()
    before = b.players()
    top_before = sorted(before, key=lambda p: -float(p["Value"]))[:15]
    cell = f"B{cat_row}"
    b.cfg_ws.update([[True]], cell, value_input_option="USER_ENTERED")
    time.sleep(2)
    after = b.players()
    top_after = sorted(after, key=lambda p: -float(p["Value"]))[:15]
    changed = sum(1 for x, y in zip(before, after) if abs(float(x["Value"]) - float(y["Value"])) > 1e-9)
    check(changed > len(before) * 0.9, f"punt changed only {changed} values")
    check([p["Name"] for p in top_before] != [p["Name"] for p in top_after], "punt did not reorder top 15")
    print(f"    punting {b.cfg_ws.acell(f'A{cat_row}').value}: {changed} values changed; "
          f"new #1 {top_after[0]['Name']} (was {top_before[0]['Name']})")
    b.cfg_ws.update([[False]], cell, value_input_option="USER_ENTERED")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=None)
    ap.add_argument("--scenarios", default="12:1,13:7,14:14,14:5:tab",
                    help="comma list of NumTeams:MySlot[:tab] (tab = tick Draft-tab checkboxes)")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    cfg = load_config(args.config)
    lg = cfg["league"]
    ss = open_spreadsheet(cfg, ROOT)
    b = Board(ss, max(lg["team_count_options"]) * lg["rounds"])

    # Accented / punctuated names: the dropdown source must be exactly the Players names.
    names = [p["Name"] for p in b.players()]
    dv_src = f"Players!$A$2:$A${len(names) + 1}"
    print(f"{len(names)} players; dropdown source {dv_src}; non-ASCII names: "
          f"{[x for x in names if not x.isascii()][:8]}")

    values = {}
    for i, sc in enumerate(args.scenarios.split(",")):
        parts = sc.split(":")
        n, slot = int(parts[0]), int(parts[1])
        values[n] = run_scenario(b, n, slot, lg["rounds"], args.seed + i,
                                 parts[2] if len(parts) > 2 else "log")

    if len(values) > 1:
        ns = sorted(values)
        some = next(iter(values[ns[0]]))
        diffs = {nn: values[nn][some] for nn in ns}
        check(len(set(round(v, 6) for v in diffs.values())) == len(ns),
              f"Value of {some} identical across team counts: {diffs}")
        print(f"\nValue of {some} by team count: {diffs}")

    # Find the FT% punt row on Config.
    col_a = b.cfg_ws.col_values(1)
    punt_test(b, col_a.index("FT%") + 1)

    print("\n=== reset for the real draft ===")
    b.clear_log()
    b.set_config(NumTeams=lg["num_teams"], MySlot=lg["my_slot"])
    st = b.named("CurrentPick", "TotalPicks")
    check(st["CurrentPick"] == 1, "Log not empty after reset")
    print(f"    Log cleared; NumTeams={lg['num_teams']}, MySlot={lg['my_slot']}, TotalPicks={st['TotalPicks']}")

    print("\n" + ("ALL CHECKS PASSED" if not FAILS else f"{len(FAILS)} CHECK(S) FAILED"))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()

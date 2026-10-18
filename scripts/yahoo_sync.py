"""Yahoo draft -> Log tab, live.

  python scripts/yahoo_sync.py auth            # print the Yahoo sign-in link
  python scripts/yahoo_sync.py code '<url>'    # paste the localhost URL you land on
  python scripts/yahoo_sync.py check [--apply] # league, teams, draft order (--apply sets NumTeams/MySlot)
  python scripts/yahoo_sync.py poll            # copy picks into the Log as they happen

The poller only fills empty Log rows; a hand-typed pick that disagrees with Yahoo is
reported, never overwritten. Players missing from the Players tab are written with
Yahoo's name so CurrentPick still advances.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rapidfuzz import fuzz, process  # noqa: E402

from draftboard import ROOT, load_config  # noqa: E402
from draftboard.names import normalize_name  # noqa: E402
from draftboard.yahoo import TEAM_MAP  # noqa: E402
from draftboard.yahoo_api import YahooClient  # noqa: E402

APP = ROOT / "secrets/yahoo_app.json"
TOKEN = ROOT / "secrets/yahoo_token.json"


class NameResolver:
    """Yahoo full name (+ team) -> exact name on the Players tab."""

    def __init__(self, names: list[str], teams: list[str]):
        self.by_norm: dict[str, list[tuple[str, str]]] = {}
        for n, t in zip(names, teams):
            self.by_norm.setdefault(normalize_name(n), []).append((n, t))
        self.norms = list(self.by_norm)

    def __call__(self, name: str, team: str) -> tuple[str, bool]:
        team = TEAM_MAP.get(team, team)
        n = normalize_name(name)
        cands = self.by_norm.get(n)
        if not cands:
            hit = process.extractOne(n, self.norms, scorer=fuzz.token_sort_ratio)
            if hit and hit[1] >= 88:
                cands = self.by_norm[hit[0]]
        if not cands:
            return name, False
        same = [c for c, t in cands if t == team]
        return (same or [c for c, _ in cands])[0], True


def players_tab(ss) -> tuple[list[str], list[str]]:
    rows = ss.worksheet("Players").get("A1:Z")
    hdr = rows[0]
    i_name, i_team = hdr.index("Name"), hdr.index("Team")
    data = [r for r in rows[1:] if r and r[0]]
    return [r[i_name] for r in data], [r[i_team] if len(r) > i_team else "" for r in data]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["auth", "code", "check", "poll"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--league", default=None, help="Yahoo league id (default: config yahoo.league_id)")
    ap.add_argument("--apply", action="store_true", help="check: write NumTeams/MySlot to Config")
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--dry-run", action="store_true", help="poll: print, don't write")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()
    cfg = load_config(args.config)
    y = YahooClient(APP, TOKEN)

    if args.cmd == "auth":
        print(y.auth_url())
        return
    if args.cmd == "code":
        y.exchange(args.arg)
        print("authorized; token saved to secrets/yahoo_token.json")
        return

    league_id = args.league or cfg.get("yahoo", {}).get("league_id")
    lkey = y.league_key(league_id)
    info = y.league_info(lkey)
    if args.cmd == "check":
        print(f"{info['name']} ({lkey}): {info['num_teams']} teams, draft {info['draft_status']} "
              f"({info['draft_type']})")
        for t in sorted(info["teams"], key=lambda t: t["draft_position"] or 99):
            print(f"  slot {t['draft_position'] or '?':>2}  {t['name']}{'   <- you' if t['mine'] else ''}")
        mine = next((t for t in info["teams"] if t["mine"]), None)
        if args.apply:
            from draftboard.gsheet import open_spreadsheet
            ss = open_spreadsheet(cfg, ROOT)
            data = [{"range": "NumTeams", "values": [[info["num_teams"]]]}]
            if mine and mine["draft_position"]:
                data.append({"range": "MySlot", "values": [[mine["draft_position"]]]})
            ss.values_batch_update({"valueInputOption": "USER_ENTERED", "data": data})
            print("Config updated:", {d["range"]: d["values"][0][0] for d in data})
        return

    # ---------------------------------------------------------------- poll
    from draftboard.gsheet import open_spreadsheet
    ss = open_spreadsheet(cfg, ROOT)
    log = ss.worksheet("Log")
    resolve = NameResolver(*players_tab(ss))
    max_picks = max(cfg["league"]["team_count_options"]) * cfg["league"]["rounds"]
    total = info["num_teams"] * cfg["league"]["rounds"]
    cache: dict[str, dict] = {}
    warned: set[int] = set()
    written = 0
    print(f"polling {info['name']} every {args.interval:.0f}s; {total} picks expected")
    while True:
        try:
            picks = [p for p in y.draft_results(lkey) if p["player_key"]]
            new_keys = [p["player_key"] for p in picks if p["player_key"] not in cache]
            if new_keys:
                cache.update(y.players(lkey, new_keys))
            col = log.get(f"D2:D{max_picks + 1}")
            current = [(r[0] if r else "") for r in col] + [""] * max_picks
            updates = []
            for p in picks:
                pl = cache.get(p["player_key"], {"name": p["player_key"], "team": ""})
                name, known = resolve(pl["name"], pl["team"])
                have = current[p["pick"] - 1]
                if not have:
                    updates.append({"range": f"Log!D{p['pick'] + 1}", "values": [[name]]})
                    tag = "" if known else "   (not on Players tab - written as Yahoo's name)"
                    print(f"  pick {p['pick']:3d}  {name}{tag}")
                elif have != name and p["pick"] not in warned:
                    warned.add(p["pick"])
                    print(f"  ! pick {p['pick']}: Log has {have!r}, Yahoo says {name!r} (left as is)")
            if updates and not args.dry_run:
                ss.values_batch_update({"valueInputOption": "USER_ENTERED", "data": updates})
                written += len(updates)
            if len(picks) >= total:
                print(f"draft complete: {len(picks)} picks, {written} written by the poller")
                return
        except KeyboardInterrupt:
            return
        except Exception as e:                       # keep polling through blips
            print(f"  (poll error: {e!s:.200}; retrying)")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()

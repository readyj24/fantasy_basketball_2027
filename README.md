# Juice League Draft Board

Python turns projections + ADP into per-category z-score values, then writes a
**Google Sheet** that is the live draft board. During the draft you only touch the
Sheet: log each pick in the **Log** tab dropdown, watch the **Board** tab.

Draft: Sun Oct 18, 6:00pm PT — Yahoo live snake, 45-second picks, 12/13/14 teams,
14 rounds, 9-cat H2H (FG%, FT%, 3PTM, PTS, REB, AST, STL, BLK, A/T).

## Pipeline

```bash
pip install -r requirements.txt

# 1. Data. Save the Hashtag projections page (File > Save page as > .html) and import it:
python scripts/import_hashtag.py path/to/Hashtag_Basketball.html   # -> data/raw/projections.csv
#    Yahoo: paste the draft-room player list into data/raw/yahoo_board.txt, then
python scripts/import_yahoo.py        # -> data/raw/adp.csv (L7ADP) + data/raw/yahoo_rank.csv (XRank order)
#    Schedule: save Hashtag's NBA Schedule Grid (Yahoo weeks) as .html and run import_hashtag.py on it
#    -> data/raw/schedule.csv; becomes the Schedule tab + playoff-week games on My Team.

# 2. Valuation (z's for 12, 13 and 14 teams; prints fuzzy name matches under 95 to fix)
python scripts/build_data.py                                       # -> data/players.csv, data/values.csv

# 3. Sheet
python scripts/build_sheet.py            # Google Sheets API (service account), idempotent rebuild
python scripts/build_sheet.py --xlsx     # fallback: out/juice_draft_board.xlsx to upload to Drive

# 4. Test against the live Sheet: 3 fake drafts (12/13/14 teams), punt toggle, then clears the Log
python scripts/simulate_draft.py --scenarios 12:1,13:7,14:14
python scripts/export_cheatsheet.py      # -> out/cheatsheet.pdf

pytest -q                                # unit tests (impact math, names, layout)
```

Name fixes: add `data/name_overrides.csv` with columns `source_name,projection_name`.

## Google service account (one time)

1. https://console.cloud.google.com → create project `juice-draft`.
2. APIs & Services → Library → enable **Google Sheets API** and **Google Drive API**.
3. IAM & Admin → Service Accounts → Create (`draft-board`), skip roles.
4. The account → Keys → Add key → JSON. Save as `secrets/service_account.json` (git-ignored).
5. Create a blank Google Sheet, Share it with the service account email as **Editor**,
   and put its ID (the long part of the URL) in `config.yaml` → `gsheets.spreadsheet_id`.

## The Sheet

| Tab | What it does |
|---|---|
| **Config** | `NumTeams` (12/13/14 dropdown — switches every value live), `MySlot`, sigma settings, ADP weight, **Punt** checkboxes per category |
| **Board** | Banner (ON THE CLOCK / N picks until you), CurrentPick, MyNextPick, TargetPick, Drift, NextValue; top 40 available by Score; top 10 by Value |
| **Log** | Pick # 1–196 prefilled; round + snake team computed; **Player** dropdown (type to filter). Rows beyond TotalPicks are grayed and ignored. Your rows highlighted |
| **Players** | Static projections and z's for every team count + live Value, PAvail, Score, AdjADP, ★ |
| **My Team** | Your picks with z's, category totals vs. average team, G/F/C fill check, NBA-team concentration |
| **Schedule** | Games per NBA team per Yahoo week; `PlayoffStart`/`PlayoffEnd` on Config pick the playoff weeks summed on Players and My Team |
| **Cheatsheet** | Static rankings for balanced / punt FT% / punt AST+A/T / punt FG% (printable backup) |

### Model

- **Counting cats**: z = (x − pool mean) / pool sd. **FG%/FT%**: z of `FGA × (FG% − pool FG%)`.
  **A/T**: z of `AST − r × TO`, r = pool AST/TO. Each z × `min(1, games/75)^0.5`.
- **Pool** = top NumTeams × 14 players (iterated twice). **Replacement level**: for each of
  G/F/C, the mean z of the first 5 players eligible there ranked from pool − 16 down
  (#180 at 14 teams, #152 at 12, #166 at 13); `blended` mode subtracts the average of the
  three lines from everyone, `positional` measures each player against his easiest
  eligible line. Deliberately a bit above true waiver level, since the room drafts off
  different rankings. All three knobs are in `config.yaml`.
- **opp_rank** = w × ADP + (1 − w) × Yahoo rank. **AdjADP** = max(opp_rank + Drift, CurrentPick).
- **PAvail** = 1 − NORM.DIST(TargetPick, AdjADP, max(SigmaMin, SigmaMult × opp_rank)).
- **Position need**: My Team computes the binding G/F/C shortfall (Hall's condition over
  3G/3F/1C). Players who reduce it get `NeedWeight × short ÷ picks left` added to Score
  and show "need" on the Board; once every remaining pick must fill it, everyone else
  drops to the bottom. `NeedWeight` (Config, default 3) = 0 turns it off.
- **Score** = Value − PAvail × max(0, Value − NextValue), NextValue = the (TargetPick − CurrentPick + 1)-th
  best available Value. The `max(0, …)` keeps a low-value player who'll still be there
  from being scored above his own value.

## Choosing a punt (My Team → Punt Advisor)

For six builds (balanced, punt FT%, FG%, AST+A/T, BLK, 3PTM) the advisor projects your
end-of-draft edge over the average team in each category: your current z's, plus for each
remaining pick the ~5 available players at that depth when sorted by the build's value,
minus the average team's full roster. Each edge becomes a weekly **win %** using that
category's noise (Config → Category noise: steady REB/AST/PTS convert edges into wins,
noisy STL/FG%/FT%/A-T don't), and builds are ranked by **Win week** = P(5+ of 9).
Punted categories still count — a noisy punt still steals some weeks. A "punt" means
"stop drafting for it", which can also be a category you've already locked up.

Noise model (`valuation.category_noise`): per-game variance = phi × base (mean for counts,
att·p(1−p) for FG%/FT%), scaled to weekly team totals, plus opponent-roster spread. `phi`
defaults are estimates; `python scripts/fit_noise.py gamelogs.csv` refits them from a
season of player game logs.

- Before your 2nd–3rd pick it is mostly noise; let rounds 1–2 be best-available.
- Commit around round 3–4: tick the matching **Punt** boxes on Config so the Board
  re-sorts for that build. Untick to compare.
- Sanity check from test drafts: Giannis/Zion/Gobert → punt FT%; Trae/Harden/Garland →
  punt FG%; Wemby/Kessler/Edey → punt AST + A/T.
- At the turns (slot 1 or the last slot) you pick twice in a row: pair two players
  that fit the same build.

## Draft-day checklist

1. Config: set `NumTeams` and `MySlot` as soon as Yahoo shows the order.
2. Log each pick as it happens (Log tab, column D — start typing the name).
3. Board: take the top Score unless My Team's position check says otherwise.
   After round 2–3, check the Punt Advisor and tick Punt boxes for the leading build.
4. Keep `out/cheatsheet.pdf` open as a backup.

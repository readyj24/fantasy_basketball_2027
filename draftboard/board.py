"""Lay out the draft-board workbook: Config, Board, Log, Players, My Team, Cheatsheet.

Every live number is a Google Sheets formula, so during the draft only the Log
(and Config) are edited. Formulas stick to functions Google Sheets supports;
FILTER/SORT/ARRAY_CONSTRAIN/MINIFS are Sheets-native.
"""
from __future__ import annotations

import pandas as pd

from .model import Sheet, Validation, CondFormat, Workbook, a1, col_letter
from .valuation import CATS, CAT_LABELS

HEADER_BG = "#1F2937"
HEADER_FG = "#FFFFFF"
GRAY = "#B7B7B7"
GRAY_BG = "#EFEFEF"
MINE_BG = "#FFF2CC"
GOOD = "#D9EAD3"
BAD = "#F4CCCC"

CHEAT_BUILDS = [
    ("Balanced", []),
    ("Punt FT%", ["ft_pct"]),
    ("Punt AST + A/T", ["ast", "a_to"]),
    ("Punt FG%", ["fg_pct"]),
]


class Cols:
    """Players-tab column positions (0-based)."""

    def __init__(self, team_counts: list[int]):
        self.name, self.pos, self.value, self.score, self.adp, self.pavail, self.star = range(7)
        self.z = list(range(7, 7 + len(CATS)))                 # active z's (Board copies A..P)
        nxt = self.z[-1] + 1
        (self.drafted, self.team, self.games, self.yrank, self.opp, self.adjadp,
         self.vrank, self.arank, self.inpool) = range(nxt, nxt + 9)
        nxt += 9
        self.proj = list(range(nxt, nxt + len(CATS)))
        nxt += len(CATS)
        self.zn: dict[int, list[int]] = {}
        for n in team_counts:
            self.zn[n] = list(range(nxt, nxt + len(CATS)))
            nxt += len(CATS)
        self.pooln: dict[int, int] = {}
        for n in team_counts:
            self.pooln[n] = nxt
            nxt += 1
        self.width = nxt


def _hdr(sheet: Sheet, rng: str) -> None:
    sheet.fmt(rng, bold=True, bg=HEADER_BG, fg=HEADER_FG, align="CENTER", wrap=True)


def build_workbook(players: pd.DataFrame, stats: pd.DataFrame, cfg: dict) -> Workbook:
    lg, opp, bcfg = cfg["league"], cfg["opponents"], cfg["board"]
    counts = sorted(lg["team_count_options"])
    if counts != list(range(counts[0], counts[0] + len(counts))):
        raise ValueError("team_count_options must be consecutive (CHOOSE indexes on NumTeams)")
    rounds = lg["rounds"]
    max_picks = max(counts) * rounds
    n = len(players)
    last = n + 1                                  # last data row on Players (1-based)
    log_last = max_picks + 1
    choose_base = counts[0] - 1                   # CHOOSE(NumTeams-11, ...)
    C = Cols(counts)

    wb = Workbook()
    config = wb.add("Config")
    board = wb.add("Board")
    log = wb.add("Log")
    pl = wb.add("Players")
    my = wb.add("My Team")
    cheat = wb.add("Cheatsheet")
    board.tab_color, log.tab_color, config.tab_color = "#34A853", "#4285F4", "#FBBC04"

    def P(col: int, absolute_rows: bool = True) -> str:
        """Whole data column on Players, e.g. Players!$C$2:$C$401."""
        L = col_letter(col)
        return f"Players!${L}$2:${L}${last}"

    def LOG(col: str) -> str:
        return f"Log!${col}$2:${col}${log_last}"

    # ------------------------------------------------------------------ Config
    rows = [
        ("NumTeams", lg["num_teams"], "12 / 13 / 14 — switches every value live, no rerun"),
        ("TotalPicks", "=NumTeams*Rounds", "formula"),
        ("MySlot", lg["my_slot"], "your draft slot (Yahoo shows the order before the draft)"),
        ("SigmaMult", opp["sigma_mult"], "spread of opponents' picks around their rank"),
        ("SigmaMin", opp["sigma_min"], "minimum spread, in picks"),
        ("OppWeight", opp["adp_weight"], "opp_rank = w × ADP + (1 − w) × Yahoo rank"),
        ("Rounds", rounds, "roster spots"),
        ("DriftWindow", opp["drift_window"], "Drift = median(pick − opp_rank) over this many picks"),
        ("DriftMinPicks", opp["drift_min_picks"], "Drift = 0 until this many picks are logged"),
        ("SleeperGap", bcfg["sleeper_gap"], "★ when value rank beats ADP rank by this much"),
        ("CanWait", bcfg["can_wait_pavail"], "Board grays rows with PAvail above this"),
    ]
    config.put_row(0, 0, ["Setting", "Value", "Notes"])
    _hdr(config, "A1:C1")
    for i, (name, val, note) in enumerate(rows, start=1):
        config.put_row(i, 0, [name, val, note])
        wb.named[name] = ("Config", a1(i, 1, True))
    config.validations.append(Validation("B2", "list", [str(c) for c in counts]))
    config.validations.append(Validation("B4", "list", [str(s) for s in range(1, max(counts) + 1)]))
    config.fmt("B2:B4", bold=True, bg=MINE_BG)

    cat_row = len(rows) + 3                       # 0-based header row of the category table
    config.put_row(cat_row - 1, 0, ["Category weights — check 'Punt' to zero a category"])
    config.fmt(f"A{cat_row}", bold=True)
    config.put_row(cat_row, 0, ["Category", "Punt", "Weight"])
    _hdr(config, f"A{cat_row + 1}:C{cat_row + 1}")
    w_cells = []
    for i, cat in enumerate(CATS):
        r = cat_row + 1 + i
        config.put_row(r, 0, [CAT_LABELS[cat], False, f"=IF({a1(r, 1)},0,1)"])
        w_cells.append(a1(r, 2))
    config.validations.append(
        Validation(f"B{cat_row + 2}:B{cat_row + 1 + len(CATS)}", "checkbox"))
    wrow = cat_row + len(CATS) + 2
    config.put(wrow, 0, "WeightsRow")
    for i, ref in enumerate(w_cells):
        config.put(wrow, 1 + i, f"={ref}")
    config.put(wrow + 1, 0, "(row form of the weights, used by Players!Value)")
    wb.named["WeightsRow"] = ("Config", f"$B${wrow + 1}:${col_letter(len(CATS))}${wrow + 1}")
    config.widths = {0: 140, 1: 80, 2: 420}
    config.frozen_rows = 1

    # ------------------------------------------------------------------ Log
    log.put_row(0, 0, ["Pick", "Round", "Team", "Player (type to search)", "Mine",
                       "Active", "Counted", "Pick−Rank"])
    _hdr(log, "A1:H1")
    for i in range(max_picks):
        r = i + 1
        R = r + 1
        log.put_row(r, 0, [
            i + 1,
            f"=ROUNDUP(A{R}/NumTeams)",
            f"=IF(ISODD(B{R}),MOD(A{R}-1,NumTeams)+1,NumTeams-MOD(A{R}-1,NumTeams))",
            "",
            f"=AND(F{R},C{R}=MySlot)",
            f"=A{R}<=TotalPicks",
            f'=IF(AND(F{R},D{R}<>""),D{R},"")',
            f'=IF(G{R}="","",A{R}-IFERROR(INDEX({P(C.opp)},MATCH(G{R},{P(C.name)},0)),A{R}))',
        ])
    log.validations.append(Validation(f"D2:D{log_last}", "range", f"=Players!$A$2:$A${last}"))
    log.cond_formats.append(CondFormat(f"A2:E{log_last}", "formula", "=$F2=FALSE", bg=GRAY_BG, fg=GRAY))
    log.cond_formats.append(CondFormat(f"A2:E{log_last}", "formula", "=$E2=TRUE", bg=MINE_BG, bold=True))
    log.hidden_cols = [5, 6, 7]
    log.widths = {0: 50, 1: 55, 2: 50, 3: 240, 4: 55}
    log.frozen_rows = 1

    # ------------------------------------------------------------------ Players
    zlabels = [f"z {CAT_LABELS[c]}" for c in CATS]
    header = [""] * C.width
    header[C.name:C.star + 1] = ["Name", "Pos", "Value", "Score", "ADP", "PAvail", "★"]
    for i, c in enumerate(C.z):
        header[c] = zlabels[i]
    header[C.drafted:C.inpool + 1] = ["Drafted", "Team", "Games", "Yahoo rank", "Opp rank",
                                      "AdjADP", "Value rank", "ADP rank", "In pool"]
    for i, c in enumerate(C.proj):
        header[c] = CAT_LABELS[CATS[i]]
    for nt in counts:
        for i, c in enumerate(C.zn[nt]):
            header[c] = f"z{nt} {CAT_LABELS[CATS[i]]}"
        header[C.pooln[nt]] = f"pool{nt}"
    pl.put_row(0, 0, header)
    _hdr(pl, f"A1:{col_letter(C.width - 1)}1")

    L = col_letter
    for i, row in players.reset_index(drop=True).iterrows():
        r = i + 1
        R = r + 1
        st = stats.iloc[i]
        vals: dict[int, object] = {
            C.name: row["name"],
            C.pos: row["yahoo_positions"],
            C.value: f"=SUMPRODUCT({L(C.z[0])}{R}:{L(C.z[-1])}{R},WeightsRow)",
            C.score: f"={L(C.value)}{R}-{L(C.pavail)}{R}*MAX(0,{L(C.value)}{R}-NextValue)",
            C.adp: float(row["adp"]),
            C.pavail: (f"=IF({L(C.drafted)}{R},0,1-NORM.DIST(TargetPick,{L(C.adjadp)}{R},"
                       f"MAX(SigmaMin,SigmaMult*{L(C.opp)}{R}),TRUE))"),
            C.star: f'=IF({L(C.arank)}{R}-{L(C.vrank)}{R}>=SleeperGap,"★","")',
            C.drafted: f"=COUNTIF({LOG('G')},{L(C.name)}{R})>0",
            C.team: row["team"],
            C.games: float(row["games"]),
            C.yrank: float(row["yahoo_rank"]),
            C.opp: f"=OppWeight*{L(C.adp)}{R}+(1-OppWeight)*{L(C.yrank)}{R}",
            C.adjadp: f"=MAX({L(C.opp)}{R}+Drift,CurrentPick)",
            C.vrank: f"=RANK({L(C.value)}{R},{P(C.value)})",
            C.arank: f"=RANK({L(C.adp)}{R},{P(C.adp)},1)",
            C.inpool: f"=CHOOSE(NumTeams-{choose_base},"
                      + ",".join(f"{L(C.pooln[nt])}{R}" for nt in counts) + ")",
        }
        for k, cat in enumerate(CATS):
            vals[C.z[k]] = (f"=CHOOSE(NumTeams-{choose_base},"
                            + ",".join(f"{L(C.zn[nt][k])}{R}" for nt in counts) + ")")
            vals[C.proj[k]] = float(st[cat])
            for nt in counts:
                vals[C.zn[nt][k]] = float(row[f"z{nt}_{cat}"])
        for nt in counts:
            vals[C.pooln[nt]] = bool(row[f"pool{nt}"])
        for c, v in vals.items():
            pl.put(r, c, v)

    pl.frozen_rows, pl.frozen_cols = 1, 1
    pl.widths = {C.name: 180, C.pos: 50}
    pl.fmt(f"{L(C.value)}2:{L(C.score)}{last}", number="0.00")
    pl.fmt(f"{L(C.pavail)}2:{L(C.pavail)}{last}", number="0%")
    pl.fmt(f"{L(C.z[0])}2:{L(C.z[-1])}{last}", number="0.00")
    pl.fmt(f"{L(C.opp)}2:{L(C.adjadp)}{last}", number="0.0")
    pl.fmt(f"{L(C.zn[counts[0]][0])}2:{L(C.zn[counts[-1]][-1])}{last}", number="0.00")
    pl.cond_formats.append(CondFormat(f"A2:{L(C.width - 1)}{last}", "formula",
                                      f"=${L(C.drafted)}2=TRUE", fg=GRAY, strike=True))

    # ------------------------------------------------------------------ Board
    board.set("A1", ('=IF(CurrentPick>TotalPicks,"DRAFT COMPLETE",IF(OnClock,"ON THE CLOCK — pick "&CurrentPick,'
                     'IF(MyNextPick=0,"No picks left",(MyNextPick-CurrentPick)&" picks until you  (you pick at "'
                     '&MyNextPick&", round "&ROUNDUP(MyNextPick/NumTeams)&")")))'))
    board.merges.append("A1:P1")
    board.fmt("A1:P1", bold=True, size=20, align="CENTER", bg="#CFE2F3")
    board.cond_formats.append(CondFormat("A1:P1", "formula", '=LEFT($A$1,2)="ON"', bg="#34A853", fg="#FFFFFF"))
    board.cond_formats.append(CondFormat("A1:P1", "formula", '=LEFT($A$1,5)="DRAFT"', bg="#666666", fg="#FFFFFF"))

    stat_labels = ["Current pick", "Round", "My next pick", "My following", "Target pick",
                   "Opp picks until", "Drift", "NextValue", "Teams", "My slot", "Total picks", "On clock"]
    stat_names = ["CurrentPick", None, "MyNextPick", "MyFollowingPick", "TargetPick", "PicksUntil",
                  "Drift", "NextValue", None, None, None, "OnClock"]
    minifs = (f"MINIFS({LOG('A')},{LOG('C')},MySlot,{LOG('F')},TRUE,{LOG('A')},")
    stat_formulas = [
        f'=COUNTIF({LOG("G")},"?*")+1',
        '=IF(CurrentPick>TotalPicks,"—",ROUNDUP(CurrentPick/NumTeams))',
        f'={minifs}">="&CurrentPick)',
        f'=IF(MyNextPick=0,0,{minifs}">"&MyNextPick))',
        "=IF(OnClock,IF(MyFollowingPick=0,TotalPicks+1,MyFollowingPick),IF(MyNextPick=0,TotalPicks+1,MyNextPick))",
        "=MAX(0,TargetPick-CurrentPick-IF(OnClock,1,0))",
        (f'=IF(CurrentPick-1<DriftMinPicks,0,IFERROR(MEDIAN(FILTER({LOG("H")},'
         f'{LOG("A")}>=CurrentPick-DriftWindow,{LOG("A")}<CurrentPick,{LOG("H")}<>"")),0))'),
        (f"=IFERROR(LARGE(FILTER({P(C.value)},NOT({P(C.drafted)})),"
         f"MAX(1,TargetPick-CurrentPick+1)),0)"),
        "=NumTeams", "=MySlot", "=TotalPicks",
        "=AND(CurrentPick<=TotalPicks,CurrentPick=MyNextPick)",
    ]
    board.put_row(1, 0, stat_labels)
    board.put_row(2, 0, stat_formulas)
    for i, nm in enumerate(stat_names):
        if nm:
            wb.named[nm] = ("Board", a1(2, i, True))
    board.fmt("A2:L2", bold=True, fg="#666666", size=9, align="CENTER", wrap=True)
    board.fmt("A3:L3", bold=True, size=13, align="CENTER")
    board.fmt("G3:H3", number="0.00")

    main_hdr = ["Name", "Pos", "Value", "Score", "ADP", "PAvail", "★"] + [CAT_LABELS[c] for c in CATS]
    top = 4                                         # 0-based header row of the main table
    board.put(top - 1, 0, "Best pick now (sorted by Score)  —  gray = likely still there next time")
    board.fmt(f"A{top}", bold=True, italic=True)
    board.put_row(top, 0, main_hdr)
    _hdr(board, f"A{top + 1}:P{top + 1}")
    main_rows = bcfg["main_rows"]
    first, end = top + 2, top + 1 + main_rows       # 1-based data rows
    board.put(top + 1, 0, (f'=IFERROR(ARRAY_CONSTRAIN(SORT(FILTER(Players!$A$2:$P${last},'
                           f'NOT({P(C.drafted)})),4,FALSE),{main_rows},16),"")'))
    board.fmt(f"C{first}:D{end}", number="0.00")
    board.fmt(f"E{first}:E{end}", number="0.0")
    board.fmt(f"F{first}:F{end}", number="0%")
    board.fmt(f"H{first}:P{end}", number="0.0")
    board.fmt(f"G{first}:G{end}", align="CENTER", fg="#B45F06", bold=True)
    board.cond_formats.append(CondFormat(f"A{first}:G{end}", "formula",
                                         f'=AND(ISNUMBER($F{first}),$F{first}>CanWait)', fg=GRAY, bg=GRAY_BG))
    board.cond_formats.append(CondFormat(f"H{first}:P{end}", "scale"))

    sx = 17                                          # sanity table at column R
    board.put(top - 1, sx, "Top 10 available by Value (sanity check)")
    board.fmt(f"{L(sx)}{top}", bold=True, italic=True)
    board.put_row(top, sx, ["Name", "Pos", "Value", "Score", "ADP", "PAvail"])
    _hdr(board, f"{L(sx)}{top + 1}:{L(sx + 5)}{top + 1}")
    board.put(top + 1, sx, (f'=IFERROR(ARRAY_CONSTRAIN(SORT(FILTER(Players!$A$2:$F${last},'
                            f'NOT({P(C.drafted)})),3,FALSE),{bcfg["sanity_rows"]},6),"")'))
    send = top + 1 + bcfg["sanity_rows"]
    board.fmt(f"{L(sx + 2)}{first}:{L(sx + 3)}{send}", number="0.00")
    board.fmt(f"{L(sx + 4)}{first}:{L(sx + 4)}{send}", number="0.0")
    board.fmt(f"{L(sx + 5)}{first}:{L(sx + 5)}{send}", number="0%")
    board.widths = {0: 170, 1: 45, 2: 55, 3: 55, 4: 50, 5: 55, 6: 25, sx: 170, sx + 1: 45, 16: 20}
    for c in range(7, 16):
        board.widths[c] = 44
    board.frozen_rows = 3

    # ------------------------------------------------------------------ My Team
    my.set("A1", "My team")
    my.fmt("A1", bold=True, size=14)
    my_hdr = ["Player", "Pos", "Team", "Games", "Value"] + [CAT_LABELS[c] for c in CATS]
    my.put_row(2, 0, my_hdr)
    _hdr(my, f"A3:{L(len(my_hdr) - 1)}3")
    my.set("A4", f'=IFERROR(FILTER({LOG("G")},{LOG("E")},{LOG("G")}<>""),"")')
    lookup_cols = [C.pos, C.team, C.games, C.value] + C.z
    r_first, r_last = 4, 3 + rounds
    for r in range(r_first, r_last + 1):
        for k, pc in enumerate(lookup_cols):
            my.set(f"{L(1 + k)}{r}", f'=IF($A{r}="","",INDEX({P(pc)},MATCH($A{r},{P(C.name)},0)))')
    tr = r_last + 2                                   # totals row (1-based)
    my.set(f"A{tr}", "My totals")
    my.set(f"A{tr + 1}", "Average team (scaled to my picks)")
    my.set(f"A{tr + 2}", "Me − average")
    my.set(f"C{tr}", "Players:")
    my.set(f"D{tr}", f'=COUNTIF(A{r_first}:A{r_last},"?*")')
    wb.named["MyCount"] = ("My Team", f"$D${tr}")
    for k in range(len(CATS) + 1):                    # Value + 9 cats
        colL = L(4 + k)
        pcol = C.value if k == 0 else C.z[k - 1]
        my.set(f"{colL}{tr}", f"=SUM({colL}{r_first}:{colL}{r_last})")
        my.set(f"{colL}{tr + 1}",
               f"=SUMPRODUCT({P(pcol)}*({P(C.inpool)}=TRUE))/NumTeams*MyCount/Rounds")
        my.set(f"{colL}{tr + 2}", f"={colL}{tr}-{colL}{tr + 1}")
    my.fmt(f"E{r_first}:{L(4 + len(CATS))}{tr + 2}", number="0.00")
    my.fmt(f"A{tr}:{L(4 + len(CATS))}{tr + 2}", bold=True)
    diff_rng = f"E{tr + 2}:{L(4 + len(CATS))}{tr + 2}"
    my.cond_formats.append(CondFormat(diff_rng, "formula", f"=E{tr + 2}>=0", bg=GOOD))
    my.cond_formats.append(CondFormat(diff_rng, "formula", f"=E{tr + 2}<0", bg=BAD))
    my.cond_formats.append(CondFormat(f"F{r_first}:{L(4 + len(CATS))}{r_last}", "scale"))

    # Positions: Hall's condition over the G/F/C starting slots (Util takes anyone).
    pr = tr + 4
    need = lg["starting_slots"]
    B = f"$B${r_first}:$B${r_last}"

    def elig(*ps: str) -> str:
        inner = "+".join(f'ISNUMBER(SEARCH("{p}",{B}))' for p in ps)
        return f"=SUMPRODUCT(--(({inner})>0))"

    my.set(f"A{pr}", "Positions")
    my.fmt(f"A{pr}", bold=True, size=12)
    my.put_row(pr, 0, ["Eligible for", "Have", "Starting slots", "Short by", "Need"])
    _hdr(my, f"A{pr + 1}:E{pr + 1}")
    subsets = [("G",), ("F",), ("C",), ("G", "F"), ("G", "C"), ("F", "C"), ("G", "F", "C")]
    for i, ss in enumerate(subsets):
        r = pr + 2 + i
        slots = sum(need[p] for p in ss)
        my.put_row(r - 1, 0, [" or ".join(ss), elig(*ss), slots, f"=MAX(0,C{r}-B{r})",
                              f'=IF(D{r}>0,A{r}&" ×"&D{r},"")'])
    s_first, s_last = pr + 2, pr + 1 + len(subsets)
    short = f"MAX(D{s_first}:D{s_last})"
    needs = f'TEXTJOIN(", ",TRUE,E{s_first}:E{s_last})'
    sr = s_last + 1
    my.set(f"A{sr}", "Picks left")
    my.set(f"B{sr}", "=Rounds-MyCount")
    my.set(f"A{sr + 1}", "Status")
    my.set(f"B{sr + 1}", (f'=IF({short}>B{sr},"⚠ CAN\'T fill 3G/3F/1C — short by "&{short}&" with "&B{sr}&" picks left",'
                          f'IF({short}=0,"OK — 3G/3F/1C covered",'
                          f'IF({short}=B{sr},"⚠ Every remaining pick must fill: ","Still need: ")&{needs}))'))
    my.fmt(f"B{sr + 1}", bold=True)
    my.cond_formats.append(CondFormat(f"B{sr + 1}", "formula", f'=LEFT(B{sr + 1},1)="⚠"', bg=BAD))
    my.cond_formats.append(CondFormat(f"B{sr + 1}", "formula", f'=LEFT(B{sr + 1},2)="OK"', bg=GOOD))
    my.cond_formats.append(CondFormat(f"D{s_first}:D{s_last}", "formula", f"=D{s_first}>0", bg=BAD))

    # NBA team concentration
    tr2 = sr + 4
    my.set(f"A{tr2}", "NBA team concentration")
    my.fmt(f"A{tr2}", bold=True, size=12)
    my.put_row(tr2, 0, ["NBA team", "My players"])
    _hdr(my, f"A{tr2 + 1}:B{tr2 + 1}")
    my.set(f"A{tr2 + 2}", f'=IFERROR(SORT(UNIQUE(FILTER(C{r_first}:C{r_last},C{r_first}:C{r_last}<>""))),"")')
    for r in range(tr2 + 2, tr2 + 2 + rounds):
        my.set(f"B{r}", f'=IF(A{r}="","",COUNTIF($C${r_first}:$C${r_last},A{r}))')
    my.cond_formats.append(CondFormat(f"A{tr2 + 2}:B{tr2 + 1 + rounds}", "formula",
                                      f'=AND(ISNUMBER($B{tr2 + 2}),$B{tr2 + 2}>=3)', bg=BAD, bold=True))
    my.widths = {0: 190, 1: 60, 2: 90, 3: 60}
    my.frozen_rows = 3

    # ------------------------------------------------------------------ Cheatsheet
    nt = lg["num_teams"]
    cheat.set("A1", f"Juice League cheatsheet — static values for {nt} teams "
                    f"(built {pd.Timestamp.now(tz='America/Los_Angeles'):%a %b %d %I:%M%p} PT)")
    cheat.fmt("A1", bold=True, size=12)
    depth = min(len(players), nt * rounds + 30)
    for b, (label, punts) in enumerate(CHEAT_BUILDS):
        c0 = b * 5
        cheat.put(2, c0, label)
        cheat.fmt(f"{L(c0)}3", bold=True, size=11)
        cheat.put_row(3, c0, ["#", "Name", "Value", "ADP"])
        _hdr(cheat, f"{L(c0)}4:{L(c0 + 3)}4")
        cats = [c for c in CATS if c not in punts]
        v = players[[f"z{nt}_{c}" for c in cats]].sum(axis=1)
        order = v.sort_values(ascending=False).index[:depth]
        for i, idx in enumerate(order):
            cheat.put_row(4 + i, c0, [i + 1, players.at[idx, "name"], round(float(v[idx]), 2),
                                      round(float(players.at[idx, "adp"]), 1)])
        cheat.widths.update({c0: 30, c0 + 1: 150, c0 + 2: 50, c0 + 3: 45, c0 + 4: 12})
    cheat.frozen_rows = 4
    return wb

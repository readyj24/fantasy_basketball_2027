import pandas as pd

from draftboard.yahoo import match_to_projections, parse_board

PASTE = """Queue\tPlayer\tXRank\tRank\t💎 L7ADP\tGP\tFG%\tFT%\t3PTM\tPTS\tREB\tAST\tST\tBLK\tA/T

V. Wembanyama
V. Wembanyama
C
SAS
1.8\t3\t2.1\t68\t.519\t.822\t130\t1750\t775\t230\t69\t230\t1.2
Your Turn - 11th Pick

B. Adebayo
B. Adebayo
Q
F,C
MIA
25\t39\t25.3\t74\t.449\t.770\t150\t1502\t638\t272\t88\t53\t2

I. Stewart
I. Stewart
O
F,C
MEM
148.5\t164\t-\t68\t.539\t.756\t60\t790\t439\t112\t26\t105\t1.3

J. Williams
J. Williams
F
OKC
33.8\t29\t40.5\t69\t.495\t.810\t97\t1393\t346\t364\t97\t38\t2.6

K. Towns
K. Towns
F,C
NYK
16.5\t25\t15.6\t73\t.509\t.852\t126\t1519\t834\t256\t63\t43\t1.4
"""


def test_parse_board():
    b = parse_board(PASTE)
    assert b["yahoo_name"].tolist() == ["V. Wembanyama", "B. Adebayo", "I. Stewart", "J. Williams", "K. Towns"]
    assert b["status"].tolist() == ["", "Q", "O", "", ""]
    assert b["team"].tolist() == ["SA", "MIA", "MEM", "OKC", "NY"]
    assert b.loc[1, "positions"] == "F,C"
    assert b.loc[2, "l7adp"] is None or pd.isna(b.loc[2, "l7adp"])
    assert b.loc[0, "xrank"] == 1.8 and b.loc[0, "rank"] == 3


def test_match_initials_and_ties():
    proj = pd.DataFrame({"name": ["Victor Wembanyama", "Jalen Williams", "Karl-Anthony Towns",
                                  "Bam Adebayo", "Isaiah Stewart", "Jaylin Williams"],
                         "team": ["SA", "OKC", "NY", "MIA", "MEM", "OKC"]})
    m = match_to_projections(parse_board(PASTE), proj)
    assert m.tolist() == ["Victor Wembanyama", "Bam Adebayo", "Isaiah Stewart", "Jalen Williams",
                          "Karl-Anthony Towns"]

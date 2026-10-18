from draftboard.ingest import to_gfc
from draftboard.names import fuzzy_map, normalize_name


def test_normalize():
    assert normalize_name("Luka Dončić") == "luka doncic"
    assert normalize_name("Jaren Jackson Jr.") == "jaren jackson"
    assert normalize_name("Royce O'Neale") == "royce oneale"
    assert normalize_name("Nikola Jokić (DEN - C)") == "nikola jokic"
    assert normalize_name("Shai Gilgeous-Alexander") == "shai gilgeous alexander"
    assert normalize_name("Robert Williams III") == "robert williams"


def test_fuzzy_map():
    proj = ["Luka Dončić", "Jaren Jackson Jr.", "Alperen Şengün", "Nic Claxton"]
    src = ["Luka Doncic", "Jaren Jackson", "Alperen Sengun", "Nicolas Claxton", "Nobody Atall"]
    m, rep = fuzzy_map(src, proj, min_accept=60)
    assert m["Luka Doncic"] == "Luka Dončić"
    assert m["Jaren Jackson"] == "Jaren Jackson Jr."
    assert m["Alperen Sengun"] == "Alperen Şengün"
    assert m["Nicolas Claxton"] == "Nic Claxton"
    assert "Nobody Atall" not in m


def test_positions():
    assert to_gfc("PG,SG") == "G"
    assert to_gfc("SF,PF,C") == "F,C"
    assert to_gfc("G,F") == "G,F"
    assert to_gfc("C") == "C"

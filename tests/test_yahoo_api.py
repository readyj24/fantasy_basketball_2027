import xml.etree.ElementTree as ET

from draftboard.yahoo_api import _strip_ns
from scripts.yahoo_sync import NameResolver

NS = "http://fantasysports.yahooapis.com/fantasy/v2/base.rng"


def test_draftresults_xml_shape():
    xml = f"""<fantasy_content xmlns="{NS}"><league><draft_results count="2">
      <draft_result><pick>1</pick><round>1</round><team_key>466.l.75810.t.3</team_key>
        <player_key>466.p.5352</player_key></draft_result>
      <draft_result><pick>2</pick><round>1</round><team_key>466.l.75810.t.7</team_key></draft_result>
    </draft_results></league></fantasy_content>"""
    root = _strip_ns(ET.fromstring(xml))
    picks = [(d.findtext("pick"), d.findtext("player_key")) for d in root.iter("draft_result")]
    assert picks == [("1", "466.p.5352"), ("2", None)]


def test_name_resolver():
    r = NameResolver(["Nikola Jokić", "Jalen Williams", "Jaylin Williams", "Jaren Jackson Jr."],
                     ["DEN", "OKC", "OKC", "UTA"])
    assert r("Nikola Jokic", "DEN") == ("Nikola Jokić", True)
    assert r("Jaren Jackson", "UTA") == ("Jaren Jackson Jr.", True)
    assert r("Jaylin Williams", "OKC") == ("Jaylin Williams", True)
    assert r("Some Rookie", "BOS") == ("Some Rookie", False)

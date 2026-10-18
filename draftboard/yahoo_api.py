"""Minimal Yahoo Fantasy Sports API client (OAuth2, XML responses)."""
from __future__ import annotations

import base64
import json
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
API = "https://fantasysports.yahooapis.com/fantasy/v2"


def _strip_ns(root: ET.Element) -> ET.Element:
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


class YahooClient:
    def __init__(self, app_file: Path, token_file: Path):
        self.app = json.loads(app_file.read_text())
        self.token_file = token_file
        self.token = json.loads(token_file.read_text()) if token_file.exists() else None

    # ---------------------------------------------------------------- auth
    def auth_url(self) -> str:
        q = {"client_id": self.app["client_id"], "redirect_uri": self.app["redirect_uri"],
             "response_type": "code", "language": "en-us", "scope": "fspt-r"}
        return f"{AUTH_URL}?{urllib.parse.urlencode(q)}"

    def _token_request(self, data: dict) -> None:
        basic = base64.b64encode(f"{self.app['client_id']}:{self.app['client_secret']}".encode()).decode()
        r = requests.post(TOKEN_URL, data=data, timeout=20,
                          headers={"Authorization": f"Basic {basic}",
                                   "Content-Type": "application/x-www-form-urlencoded"})
        r.raise_for_status()
        tok = r.json()
        tok["expires_at"] = time.time() + int(tok.get("expires_in", 3600)) - 120
        if "refresh_token" not in tok and self.token:
            tok["refresh_token"] = self.token["refresh_token"]
        self.token = tok
        self.token_file.write_text(json.dumps(tok))
        self.token_file.chmod(0o600)

    def exchange(self, code_or_url: str) -> None:
        code = code_or_url
        if "code=" in code_or_url:
            code = urllib.parse.parse_qs(urllib.parse.urlparse(code_or_url).query)["code"][0]
        self._token_request({"grant_type": "authorization_code", "code": code.strip(),
                             "redirect_uri": self.app["redirect_uri"]})

    def _refresh(self) -> None:
        self._token_request({"grant_type": "refresh_token", "refresh_token": self.token["refresh_token"],
                             "redirect_uri": self.app["redirect_uri"]})

    # ---------------------------------------------------------------- requests
    def get(self, path: str) -> ET.Element:
        if not self.token:
            raise RuntimeError("not authorized yet: run yahoo_sync.py auth")
        if time.time() > self.token.get("expires_at", 0):
            self._refresh()
        for attempt in range(3):
            r = requests.get(f"{API}/{path}", timeout=20,
                             headers={"Authorization": f"Bearer {self.token['access_token']}"})
            if r.status_code == 401 and attempt == 0:
                self._refresh()
                continue
            if r.status_code in (429, 500, 502, 503, 999) and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            r.raise_for_status()
            return _strip_ns(ET.fromstring(r.content))
        raise RuntimeError(f"GET {path} failed")

    # ---------------------------------------------------------------- fantasy
    def league_key(self, league_id: str | int) -> str:
        game = self.get("game/nba")
        return f"{game.findtext('.//game_key')}.l.{league_id}"

    def league_info(self, lkey: str) -> dict:
        s = self.get(f"league/{lkey}/settings")
        teams = self.get(f"league/{lkey}/teams")
        out = {
            "name": s.findtext(".//league/name"),
            "num_teams": int(s.findtext(".//league/num_teams") or 0),
            "draft_status": s.findtext(".//league/draft_status"),
            "draft_type": s.findtext(".//settings/draft_type"),
            "teams": [],
        }
        for t in teams.iter("team"):
            out["teams"].append({
                "team_key": t.findtext("team_key"),
                "name": t.findtext("name"),
                "draft_position": int(t.findtext("draft_position") or 0) or None,
                "mine": t.findtext("is_owned_by_current_login") == "1",
            })
        return out

    def draft_results(self, lkey: str) -> list[dict]:
        root = self.get(f"league/{lkey}/draftresults")
        picks = []
        for d in root.iter("draft_result"):
            picks.append({"pick": int(d.findtext("pick")), "round": int(d.findtext("round") or 0),
                          "team_key": d.findtext("team_key"), "player_key": d.findtext("player_key")})
        return sorted(picks, key=lambda p: p["pick"])

    def players(self, lkey: str, keys: list[str]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for i in range(0, len(keys), 25):
            chunk = ",".join(keys[i:i + 25])
            root = self.get(f"league/{lkey}/players;player_keys={chunk}")
            for p in root.iter("player"):
                out[p.findtext("player_key")] = {
                    "name": p.findtext("name/full"),
                    "team": (p.findtext("editorial_team_abbr") or "").upper(),
                    "positions": p.findtext("display_position") or "",
                }
        return out

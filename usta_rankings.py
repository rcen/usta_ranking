#!/usr/bin/env python3
"""
USTA Tournament Standings & Rankings Generator (All-in-One Standalone Script)
No external dependencies required (uses only Python 3 standard library).

Usage:
    python usta_rankings.py
    python usta_rankings.py "https://playtennis.usta.com/.../players/<tournament-id>"
    python usta_rankings.py <tournament-id> --list-name "Boys' 12 National Standings List (combined)"
"""

import os
import sys
import re
import json
import urllib.request
import urllib.error
import hmac
import hashlib
import argparse
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict, Any, Callable, Set

def load_tracked_players(config_path: Optional[str] = None) -> Set[str]:
    """
    Loads tracked player names and USTA IDs from a text configuration file.
    Each row contains a player's name or numeric USTA ID.
    Ignores empty lines and comments starting with '#'.
    """
    path_to_try = config_path
    if not path_to_try:
        candidates = [
            "tracked_players.txt",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "tracked_players.txt"),
            "watchlist.txt",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchlist.txt"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                path_to_try = c
                break

    if not path_to_try or not os.path.isfile(path_to_try):
        return set()

    tracked = set()
    try:
        with open(path_to_try, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                tracked.add(line.lower())
    except Exception as e:
        print(f"Warning: Could not read tracked players file '{path_to_try}': {e}", file=sys.stderr)

    return tracked


def is_player_tracked(player: Dict[str, Any], tracked_set: Set[str]) -> bool:
    """Checks if a player matches any tracked USTA ID or name."""
    if not tracked_set:
        return False

    uid = str(player.get("usta_id") or "").strip().lower()
    if uid and uid in tracked_set:
        return True

    name = (player.get("name") or "").strip().lower()
    if name and name in tracked_set:
        return True

    # Also match reversed name (e.g. "He, Austin" vs "Austin He")
    cleaned_name_parts = re.split(r"[\s,]+", name)
    cleaned_name_sorted = " ".join(sorted(filter(None, cleaned_name_parts)))
    for t in tracked_set:
        t_parts = re.split(r"[\s,]+", t)
        if " ".join(sorted(filter(None, t_parts))) == cleaned_name_sorted:
            return True

    return False

try:
    from utr_api import get_player_utr
except ImportError:
    # Embedded fallback for get_player_utr to keep script 100% standalone
    def get_player_utr(name: str, city: Optional[str] = None, state: Optional[str] = None, timeout: int = 8) -> Dict[str, Any]:
        import urllib.parse
        clean_name = name.strip()
        if not clean_name:
            return {}
        try:
            url = f"https://app.utrsports.net/api/v2/search/players?query={urllib.parse.quote(clean_name)}"
            headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Referer": "https://app.utrsports.net/"}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            hits = data.get("hits") or []
            if not hits:
                return {}
            # Match best candidate by location if provided
            pid = str(hits[0].get("id") or "").strip()
            if city or state:
                for h in hits:
                    loc = ((h.get("source") or {}).get("location") or {}).get("display", "").lower()
                    if (city and city.lower() in loc) or (state and state.lower() in loc):
                        pid = str(h.get("id") or "").strip()
                        break
            if not pid:
                return {}
            v2_url = f"https://app.utrsports.net/api/v2/player/{pid}"
            req2 = urllib.request.Request(v2_url, headers=headers)
            with urllib.request.urlopen(req2, timeout=timeout) as r2:
                d2 = json.loads(r2.read().decode("utf-8"))
            s_disp = d2.get("singlesUtrDisplay") or str(d2.get("singlesUtr") or "")
            d_disp = d2.get("doublesUtrDisplay") or str(d2.get("doublesUtr") or "")
            return {
                "utr_id": pid,
                "singles_utr": float(s_disp) if s_disp and s_disp != "0.00" else None,
                "singles_utr_display": s_disp if s_disp and s_disp != "0.00" else "Unrated",
                "doubles_utr": float(d_disp) if d_disp and d_disp != "0.00" else None,
                "doubles_utr_display": d_disp if d_disp and d_disp != "0.00" else "Unrated",
                "singles_reliability": d2.get("ratingProgressSingles"),
                "doubles_reliability": d2.get("ratingProgressDoubles"),
                "profile_url": f"https://app.utrsports.net/profiles/{pid}",
            }
        except Exception:
            return {}

# Ensure safe UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


CLUBSPARK_GRAPHQL_URL = "https://prd-usta-kube-tournaments.clubspark.pro/graphql"
USTA_RANKINGS_API_URL = "https://www.usta.com/usta/api?type=playerRankings"
USTA_API_HMAC_SECRET = b"89Wd0xPoep"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_TARGET_LIST = "Boys' 12 National Standings List (combined)"
UUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def resolve_target_list(user_arg: Optional[str], tournament_name: str = "") -> str:
    """
    Resolves the target ranking list from user argument or auto-detects from tournament name.
    Supports shortcuts like '10', '12', '14', '16', '18', 'b14', 'g14', 'boys 14', etc.
    """
    if user_arg:
        arg_clean = user_arg.strip().lower()
        shortcut_map = {
            "10": "Boys' 10 National Standings List (combined)",
            "b10": "Boys' 10 National Standings List (combined)",
            "b10s": "Boys' 10 National Standings List (combined)",
            "10u": "Boys' 10 National Standings List (combined)",
            "boys 10": "Boys' 10 National Standings List (combined)",
            "boys' 10": "Boys' 10 National Standings List (combined)",
            "g10": "Girls' 10 National Standings List (combined)",
            "g10s": "Girls' 10 National Standings List (combined)",
            "10g": "Girls' 10 National Standings List (combined)",
            "girls 10": "Girls' 10 National Standings List (combined)",
            "girls' 10": "Girls' 10 National Standings List (combined)",

            "12": "Boys' 12 National Standings List (combined)",
            "b12": "Boys' 12 National Standings List (combined)",
            "b12s": "Boys' 12 National Standings List (combined)",
            "12u": "Boys' 12 National Standings List (combined)",
            "boys 12": "Boys' 12 National Standings List (combined)",
            "boys' 12": "Boys' 12 National Standings List (combined)",
            "g12": "Girls' 12 National Standings List (combined)",
            "g12s": "Girls' 12 National Standings List (combined)",
            "12g": "Girls' 12 National Standings List (combined)",
            "girls 12": "Girls' 12 National Standings List (combined)",
            "girls' 12": "Girls' 12 National Standings List (combined)",

            "14": "Boys' 14 National Standings List (combined)",
            "b14": "Boys' 14 National Standings List (combined)",
            "b14s": "Boys' 14 National Standings List (combined)",
            "14u": "Boys' 14 National Standings List (combined)",
            "boys 14": "Boys' 14 National Standings List (combined)",
            "boys' 14": "Boys' 14 National Standings List (combined)",
            "g14": "Girls' 14 National Standings List (combined)",
            "g14s": "Girls' 14 National Standings List (combined)",
            "14g": "Girls' 14 National Standings List (combined)",
            "girls 14": "Girls' 14 National Standings List (combined)",
            "girls' 14": "Girls' 14 National Standings List (combined)",

            "16": "Boys' 16 National Standings List (combined)",
            "b16": "Boys' 16 National Standings List (combined)",
            "b16s": "Boys' 16 National Standings List (combined)",
            "16u": "Boys' 16 National Standings List (combined)",
            "boys 16": "Boys' 16 National Standings List (combined)",
            "boys' 16": "Boys' 16 National Standings List (combined)",
            "g16": "Girls' 16 National Standings List (combined)",
            "g16s": "Girls' 16 National Standings List (combined)",
            "16g": "Girls' 16 National Standings List (combined)",
            "girls 16": "Girls' 16 National Standings List (combined)",
            "girls' 16": "Girls' 16 National Standings List (combined)",

            "18": "Boys' 18 National Standings List (combined)",
            "b18": "Boys' 18 National Standings List (combined)",
            "b18s": "Boys' 18 National Standings List (combined)",
            "18u": "Boys' 18 National Standings List (combined)",
            "boys 18": "Boys' 18 National Standings List (combined)",
            "boys' 18": "Boys' 18 National Standings List (combined)",
            "g18": "Girls' 18 National Standings List (combined)",
            "g18s": "Girls' 18 National Standings List (combined)",
            "18g": "Girls' 18 National Standings List (combined)",
            "girls 18": "Girls' 18 National Standings List (combined)",
            "girls' 18": "Girls' 18 National Standings List (combined)",
        }
        if arg_clean in shortcut_map:
            return shortcut_map[arg_clean]
        return user_arg

    # Auto-detect age division from tournament name if not explicitly specified
    if tournament_name:
        m = re.search(r'\b(10|12|14|16|18)\s*(?:s|\'s|u|\s*&\s*under|\s*and\s*under)?\b', tournament_name, re.I)
        if m:
            age = m.group(1)
            is_girls_only = bool(
                re.search(r'\bgirls?\b|\bg(10|12|14|16|18)\b', tournament_name, re.I)
                and not re.search(r'\bboys?\b|\bb/g\b|\bg/b\b', tournament_name, re.I)
            )
            gender = "Girls'" if is_girls_only else "Boys'"
            return f"{gender} {age} National Standings List (combined)"

    return DEFAULT_TARGET_LIST


def extract_tournament_id(url_or_id: str) -> str:
    """
    Extracts a tournament UUID from a full URL, validates an existing UUID,
    or automatically resolves a USTA Sanction Tournament ID (e.g. '26-17452') via search.
    """
    clean_input = url_or_id.strip()
    match = UUID_PATTERN.search(clean_input)
    if match:
        return match.group(0).upper()

    # Search via USTA Unified Search API for sanction codes (e.g. 26-17452)
    try:
        import urllib.parse
        encoded = urllib.parse.quote(clean_input)
        search_url = f"https://prd-usta-kube.clubspark.pro/unified-search-api/api/Search/tournaments/TextQuery?indexSchema=tournament&text={encoded}"
        req = urllib.request.Request(
            search_url,
            headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("items") or []
            if items and "id" in items[0]:
                return items[0]["id"].upper()
    except Exception:
        pass

    raise ValueError(f"Could not find tournament for input: '{url_or_id}'. Provide a tournament URL, UUID, or Sanction ID (e.g. 26-17452).")


def fetch_tournament_details(tournament_id: str, timeout: int = 15) -> Dict[str, Any]:
    """Fetches tournament details (name, venue, sanction status, identification code) via Clubspark GraphQL."""
    tournament_id = extract_tournament_id(tournament_id)
    query = """
    query GetTournament($id: UUID!, $previewMode: Boolean) {
      publishedTournament(id: $id, previewMode: $previewMode) {
        id
        identificationCode
        name
        sanctionStatus
        isPublished
        organisation {
          id
          name
        }
        events {
          id
          division {
            gender
            eventType
          }
          level {
            name
            category
          }
        }
      }
    }
    """
    payload = json.dumps({"query": query, "variables": {"id": tournament_id, "previewMode": False}}).encode("utf-8")
    req = urllib.request.Request(
        CLUBSPARK_GRAPHQL_URL,
        data=payload,
        headers={"User-Agent": DEFAULT_USER_AGENT, "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("data", {}).get("publishedTournament") or {}
    except Exception as exc:
        return {"id": tournament_id, "name": f"Tournament {tournament_id}", "error": str(exc)}


def fetch_tournament_players(tournament_id: str, timeout: int = 15) -> List[Dict[str, Any]]:
    """Fetches all registered players for a tournament with pagination."""
    tournament_id = extract_tournament_id(tournament_id)
    query = """
    query GetPlayers($id: UUID!, $queryParameters: QueryParametersPaged!) {
      paginatedPublicTournamentRegistrations(tournamentId: $id, queryParameters: $queryParameters) {
        totalItems
        items {
          firstName: playerFirstName
          gender: playerGender
          lastName: playerLastName
          city: playerCity
          state: playerState
          playerName
          playerId {
            key
            value
          }
          playerCustomIds {
            key
            value
          }
        }
      }
    }
    """
    all_players = []
    offset = 0
    limit = 100
    headers = {"User-Agent": DEFAULT_USER_AGENT, "Content-Type": "application/json", "Accept": "application/json"}

    while True:
        payload = json.dumps({
            "query": query,
            "variables": {"id": tournament_id, "queryParameters": {"offset": offset, "limit": limit}}
        }).encode("utf-8")
        req = urllib.request.Request(CLUBSPARK_GRAPHQL_URL, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        result = data.get("data", {}).get("paginatedPublicTournamentRegistrations") or {}
        total = result.get("totalItems", 0)
        items = result.get("items") or []

        for item in items:
            custom_ids = {
                entry.get("key"): entry.get("value")
                for entry in item.get("playerCustomIds", [])
                if isinstance(entry, dict) and entry.get("key")
            }
            usta_id = custom_ids.get("ustaId")
            all_players.append({
                "name": item.get("playerName") or f"{item.get('firstName', '')} {item.get('lastName', '')}".strip(),
                "city": item.get("city", ""),
                "state": item.get("state", ""),
                "usta_id": usta_id,
            })

        offset += limit
        if offset >= total or not items:
            break

    return all_players


def fetch_player_rankings(uaid: str, timeout: int = 12) -> List[Dict[str, Any]]:
    """Fetches all official ranking lists for a player UAID using HMAC-SHA256 signature."""
    if not uaid:
        return []

    payload_str = json.dumps({"selection": {"uaid": str(uaid)}}, separators=(",", ":"))
    hash_sig = hmac.new(USTA_API_HMAC_SECRET, payload_str.encode("utf-8"), hashlib.sha256).hexdigest()
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Hash": hash_sig,
        "Referer": f"https://www.usta.com/en/home/play/player-search/profile.html#uaid={uaid}&tab=rankings",
    }
    req = urllib.request.Request(USTA_RANKINGS_API_URL, data=payload_str.encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("player", {}).get("rankings") or []
    except Exception:
        return []


def fetch_tournament_roster_with_rankings(
    tournament_id: str,
    max_workers: int = 8,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
    fetch_utr: bool = True,
) -> Dict[str, Any]:
    """Fetches tournament details, all registered players, and concurrently fetches rankings and UTRs."""
    t_id = extract_tournament_id(tournament_id)
    details = fetch_tournament_details(t_id)
    players = fetch_tournament_players(t_id)

    total_players = len(players)
    completed_count = 0

    if total_players == 0:
        return {"tournament": details, "players": []}

    def _worker(player_dict: Dict[str, Any]) -> Dict[str, Any]:
        p = dict(player_dict)
        uid = p.get("usta_id")
        p["rankings"] = fetch_player_rankings(uid) if uid else []
        if fetch_utr:
            p["utr"] = get_player_utr(p.get("name", ""), city=p.get("city"), state=p.get("state"))
        else:
            p["utr"] = {}
        return p

    enriched_players = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_player = {executor.submit(_worker, p): p for p in players}
        for future in as_completed(future_to_player):
            p_res = future.result()
            enriched_players.append(p_res)
            completed_count += 1
            if on_progress:
                on_progress(completed_count, total_players, p_res.get("name", ""))

    return {"tournament": details, "players": enriched_players}


def process_player_rankings(
    players: List[Dict[str, Any]],
    target_list_name: str,
    tracked_players: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """Filters player data specifically for the target standings list and sorts by rank."""
    processed = []
    target_lower = target_list_name.strip().lower()

    for p in players:
        p_copy = dict(p)
        rankings = p.get("rankings") or []
        matched = None
        for r in rankings:
            label = (r.get("displayLabel") or "").strip().lower()
            if target_lower in label or label in target_lower:
                matched = r
                break

        if matched:
            rank_obj = matched.get("rank") or {}
            rec_obj = matched.get("record") or {}
            p_copy["has_target_rank"] = True
            p_copy["national_rank"] = rank_obj.get("national")
            p_copy["section_rank"] = rank_obj.get("section")
            p_copy["district_rank"] = rank_obj.get("district")
            p_copy["points"] = matched.get("points")
            p_copy["wins"] = rec_obj.get("win", 0)
            p_copy["losses"] = rec_obj.get("loss", 0)
            p_copy["section"] = matched.get("section") or ""
            p_copy["district"] = matched.get("district") or ""
            p_copy["trend"] = matched.get("trendDirection") or "no change"
        else:
            p_copy["has_target_rank"] = False
            p_copy["national_rank"] = None
            p_copy["section_rank"] = None
            p_copy["district_rank"] = None
            p_copy["points"] = None
            p_copy["wins"] = 0
            p_copy["losses"] = 0
            p_copy["section"] = ""
            p_copy["district"] = ""
            p_copy["trend"] = "none"

        # UTR data
        utr_info = p.get("utr") or {}
        p_copy["utr_singles"] = utr_info.get("singles_utr")
        p_copy["utr_doubles"] = utr_info.get("doubles_utr")
        p_copy["utr_singles_display"] = utr_info.get("singles_utr_display") or "-"
        p_copy["utr_doubles_display"] = utr_info.get("doubles_utr_display") or "-"
        p_copy["utr_singles_reliability"] = utr_info.get("singles_reliability")
        p_copy["utr_doubles_reliability"] = utr_info.get("doubles_reliability")
        p_copy["utr_profile_url"] = utr_info.get("profile_url")

        uaid = p.get("usta_id")
        p_copy["profile_url"] = (
            f"https://www.usta.com/en/home/play/player-search/profile.html#uaid={uaid}&tab=rankings" if uaid else None
        )
        p_copy["is_tracked"] = is_player_tracked(p_copy, tracked_players or set())
        processed.append(p_copy)

    processed.sort(key=lambda x: (0 if (x["national_rank"] is not None) else 1, x["national_rank"] or 999999, x["name"].lower()))
    return processed



def generate_html(
    tournament: Dict[str, Any],
    players: List[Dict[str, Any]],
    target_list: str,
    tracked_players: Optional[Set[str]] = None,
) -> str:
    """Creates a standalone, interactive HTML dashboard."""
    processed = process_player_rankings(players, target_list, tracked_players=tracked_players)
    total_players = len(processed)
    ranked = [p for p in processed if p["has_target_rank"]]
    best_rank = min((p["national_rank"] for p in ranked if p["national_rank"]), default="N/A")
    tracked_count = sum(1 for p in processed if p.get("is_tracked"))
    t_name = tournament.get("name") or f"Tournament {tournament.get('id', '')}"
    t_org = tournament.get("organisation", {}).get("name") or "USTA Tournament"
    t_id = tournament.get("id", "")
    t_code = tournament.get("identificationCode") or ""

    client_json = json.dumps({"tournament": tournament, "targetList": target_list, "players": processed}, indent=2)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{t_name} - Player Rankings</title>
    <style>
        :root {{ --primary: #0284c7; --primary-dark: #0369a1; --bg: #f8fafc; --card: #ffffff; --border: #e2e8f0; --text: #1e293b; --muted: #64748b; }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        body {{ background: var(--bg); color: var(--text); padding: 24px; }}
        .container {{ max-width: 1250px; margin: 0 auto; }}
        header {{ background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: white; padding: 30px; border-radius: 14px; margin-bottom: 20px; }}
        h1 {{ font-size: 1.8rem; margin: 8px 0; }}
        .sub {{ color: #94a3b8; font-size: 0.95rem; display: flex; gap: 14px; flex-wrap: wrap; }}
        .badge {{ display: inline-flex; padding: 3px 8px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }}
        .badge-court {{ background: rgba(34,197,94,0.2); color: #4ade80; border: 1px solid rgba(34,197,94,0.4); }}
        .badge-section {{ background: #fef3c7; color: #92400e; border: 1px solid #fde68a; }}
        .badge-unranked {{ background: #f1f5f9; color: #64748b; }}
        .badge-utr {{ background: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd; font-weight: 700; }}
        .tracked-star {{ display: inline-block; margin-right: 5px; font-size: 1.05rem; vertical-align: middle; }}
        tr.row-tracked {{ background-color: rgba(254, 243, 199, 0.28) !important; }}
        tr.row-tracked td {{ border-top: 2.5px solid #d97706 !important; border-bottom: 2.5px solid #d97706 !important; }}
        tr.row-tracked td:first-child {{ border-left: 2.5px solid #d97706 !important; }}
        tr.row-tracked td:last-child {{ border-right: 2.5px solid #d97706 !important; }}
        tr.row-tracked:hover td {{ background-color: rgba(254, 243, 199, 0.5) !important; }}
        .banner {{ margin-top: 14px; background: rgba(255,255,255,0.08); border-left: 4px solid #38bdf8; padding: 10px 14px; border-radius: 6px; font-size: 0.95rem; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 20px; }}
        .stat {{ background: var(--card); padding: 18px; border-radius: 10px; border: 1px solid var(--border); }}
        .stat-lbl {{ font-size: 0.75rem; font-weight: 600; color: var(--muted); text-transform: uppercase; }}
        .stat-val {{ font-size: 1.6rem; font-weight: 800; margin-top: 4px; }}
        .controls {{ background: var(--card); padding: 14px 18px; border-radius: 10px; border: 1px solid var(--border); margin-bottom: 18px; display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }}
        .controls input {{ flex: 1; min-width: 220px; padding: 8px 14px; border: 1px solid var(--border); border-radius: 6px; font-size: 0.95rem; }}
        .controls select, .controls button {{ padding: 8px 14px; border: 1px solid var(--border); border-radius: 6px; background: white; cursor: pointer; font-weight: 500; font-size: 0.9rem; }}
        .controls button {{ background: var(--primary); color: white; border: none; }}
        .controls button:hover {{ background: var(--primary-dark); }}
        .table-box {{ background: var(--card); border-radius: 10px; border: 1px solid var(--border); overflow-x: auto; }}
        table {{ width: 100%; border-collapse: collapse; text-align: left; }}
        th {{ background: #f1f5f9; color: var(--muted); font-size: 0.75rem; font-weight: 700; text-transform: uppercase; padding: 12px 14px; border-bottom: 2px solid var(--border); cursor: pointer; user-select: none; }}
        th:hover {{ background: #e2e8f0; }}
        th.sorted-asc::after {{ content: " ▲"; color: var(--primary); }}
        th.sorted-desc::after {{ content: " ▼"; color: var(--primary); }}
        td {{ padding: 12px 14px; border-bottom: 1px solid var(--border); font-size: 0.9rem; vertical-align: middle; }}
        tr:hover td {{ background: #f8fafc; }}
        .pname {{ font-weight: 700; color: #0f172a; text-decoration: none; }}
        .pname:hover {{ color: var(--primary); text-decoration: underline; }}
        .btn-view {{ padding: 3px 8px; font-size: 0.75rem; border-radius: 4px; border: 1px solid #cbd5e1; background: #f1f5f9; cursor: pointer; }}
        .btn-view:hover {{ background: #e2e8f0; }}
        .modal {{ position: fixed; inset: 0; background: rgba(15,23,42,0.6); display: none; align-items: center; justify-content: center; z-index: 99; }}
        .modal-box {{ background: white; border-radius: 12px; width: 90%; max-width: 600px; max-height: 80vh; overflow-y: auto; padding: 22px; }}
        .modal-item {{ border: 1px solid var(--border); border-radius: 6px; padding: 10px; margin-bottom: 8px; background: #f8fafc; font-size: 0.85rem; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <span class="badge badge-court">USTA Standings</span>
            <h1>{t_name}</h1>
            <div class="sub">
                <span>📍 {t_org}</span>
                <span>•</span>
                {f'<span><strong>Tournament ID:</strong> <code>{t_code}</code></span> <span>•</span>' if t_code else ''}
                <span>UUID: <code>{t_id}</code></span>
            </div>
            <div class="banner">
                <strong>Target List:</strong> <span style="color: #38bdf8;">{target_list}</span>
            </div>
        </header>

        <div class="grid">
            <div class="stat"><div class="stat-lbl">Total Players</div><div class="stat-val">{total_players}</div></div>
            <div class="stat"><div class="stat-lbl">Ranked Players</div><div class="stat-val" style="color: var(--primary);">{len(ranked)}</div></div>
            <div class="stat"><div class="stat-lbl">Top National Rank</div><div class="stat-val" style="color: #16a34a;">#{best_rank}</div></div>
            <div class="stat"><div class="stat-lbl">Unranked</div><div class="stat-val" style="color: var(--muted);">{total_players - len(ranked)}</div></div>
            {f'<div class="stat"><div class="stat-lbl">Tracked Players</div><div class="stat-val" style="color: #d97706;">★ {tracked_count}</div></div>' if tracked_count > 0 else ''}
        </div>

        <div class="controls">
            <input type="text" id="search" placeholder="Search name, city, or state...">
            <select id="statusFilter">
                <option value="all">All Players ({total_players})</option>
                <option value="ranked">Ranked Only ({len(ranked)})</option>
                <option value="unranked">Unranked Only ({total_players - len(ranked)})</option>
                {f'<option value="tracked">⭐ Tracked Only ({tracked_count})</option>' if tracked_count > 0 else ''}
            </select>
            <button onclick="exportCSV()">Export CSV</button>
        </div>

        <div class="table-box">
            <table>
                <thead>
                    <tr>
                        <th onclick="sortT('pos', this)">#</th>
                        <th onclick="sortT('name', this)">Player Name</th>
                        <th onclick="sortT('utr', this)">UTR</th>
                        <th onclick="sortT('national_rank', this)" class="sorted-asc">Nat. Rank</th>
                        <th onclick="sortT('section_rank', this)">Sec. Rank</th>
                        <th onclick="sortT('points', this)">Points</th>
                        <th onclick="sortT('record', this)">Record (W-L)</th>
                        <th onclick="sortT('city', this)">Location</th>
                        <th>All Rankings</th>
                    </tr>
                </thead>
                <tbody id="tbody"></tbody>
            </table>
        </div>
    </div>

    <div id="modal" class="modal" onclick="closeM(event)">
        <div class="modal-box" onclick="event.stopPropagation()">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                <h3 id="mName" style="font-weight:700;"></h3>
                <button onclick="closeM()" style="border:none; background:none; font-size:1.5rem; cursor:pointer;">&times;</button>
            </div>
            <div id="mList"></div>
        </div>
    </div>

    <script>
        const data = {client_json};
        let sortCol = 'national_rank', sortAsc = true;

        function render() {{
            const search = document.getElementById('search').value.toLowerCase().trim();
            const status = document.getElementById('statusFilter').value;
            let list = data.players.filter(p => {{
                if (status === 'ranked' && !p.has_target_rank) return false;
                if (status === 'unranked' && p.has_target_rank) return false;
                if (status === 'tracked' && !p.is_tracked) return false;
                if (!search) return true;
                return (p.name||'').toLowerCase().includes(search) || (p.city||'').toLowerCase().includes(search) || (p.usta_id||'').includes(search);
            }});

            list.sort((a, b) => {{
                let valA = a[sortCol];
                let valB = b[sortCol];
                if (sortCol === 'utr') {{
                    valA = a.utr_singles ?? a.utr_doubles ?? -1;
                    valB = b.utr_singles ?? b.utr_doubles ?? -1;
                }} else if (sortCol.includes('rank')) {{
                    valA = valA ?? 999999;
                    valB = valB ?? 999999;
                }} else if (sortCol.startsWith('utr_') || sortCol === 'points') {{
                    valA = valA ?? -1;
                    valB = valB ?? -1;
                }} else {{
                    valA = valA ?? '';
                    valB = valB ?? '';
                }}
                if (typeof valA === 'string') valA = valA.toLowerCase();
                if (typeof valB === 'string') valB = valB.toLowerCase();
                return (valA < valB ? -1 : 1) * (sortAsc ? 1 : -1);
            }});

            document.getElementById('tbody').innerHTML = list.map((p, idx) => {{
                const nRank = p.national_rank ? `#${{p.national_rank}}` : '<span class="badge badge-unranked">Unranked</span>';
                const sRank = p.section_rank ? `#${{p.section_rank}}` : '-';
                const pts = p.points !== null ? p.points : '-';

                let utrCell = '<span style="color:var(--muted);">-</span>';
                if (p.utr_singles || p.utr_doubles) {{
                    const badges = [];
                    if (p.utr_singles) {{
                        badges.push(`<span class="badge badge-utr" title="Singles UTR (Reliability: ${{p.utr_singles_reliability || 'N/A'}})">${{p.utr_singles_display}}</span>`);
                    }}
                    if (p.utr_doubles) {{
                        badges.push(`<span class="badge badge-utr" style="background:#f1f5f9;color:#475569;border-color:#cbd5e1;font-size:0.75rem;" title="Doubles UTR (Reliability: ${{p.utr_doubles_reliability || 'N/A'}})">D: ${{p.utr_doubles_display}}</span>`);
                    }}
                    const utrUrl = p.utr_profile_url || '#';
                    utrCell = `<a href="${{utrUrl}}" target="_blank" style="text-decoration:none; display:inline-flex; align-items:center; gap:4px;">${{badges.join('')}}</a>`;
                }}

                const rec = p.has_target_rank ? `${{p.wins}}W - ${{p.losses}}L` : '-';
                const loc = [p.city, p.state].filter(Boolean).join(', ') || '-';
                const link = p.profile_url ? `<a class="pname" href="${{p.profile_url}}" target="_blank" title="USTA ID: ${{p.usta_id || 'N/A'}}">${{p.name}} ↗</a>` : p.name;
                const rCount = (p.rankings||[]).length;
                const btn = rCount > 0 ? `<button class="btn-view" onclick="openM('${{p.usta_id}}')">All (${{rCount}})</button>` : '-';
                const isTracked = p.is_tracked;
                const starIcon = isTracked ? '<span class="tracked-star" title="Tracked Player">&#11088;</span> ' : '';
                const rowClass = isTracked ? 'class="row-tracked"' : '';

                return `<tr ${{rowClass}}>
                    <td style="color:var(--muted); font-weight:700;">${{idx + 1}}</td>
                    <td>${{starIcon}}${{link}}</td>
                    <td>${{utrCell}}</td>
                    <td>${{nRank}}</td>
                    <td>${{sRank}}</td>
                    <td>${{pts}}</td>
                    <td>${{rec}}</td>
                    <td>${{loc}}</td>
                    <td>${{btn}}</td>
                </tr>`;
            }}).join('');
        }}

        function sortT(col, elem) {{
            if (sortCol === col) {{
                sortAsc = !sortAsc;
            }} else {{
                sortCol = col;
                sortAsc = (col === 'utr' || col.startsWith('utr_') || col === 'points') ? false : true;
            }}
            document.querySelectorAll('th').forEach(t => t.classList.remove('sorted-asc', 'sorted-desc'));
            if (elem) {{
                elem.classList.add(sortAsc ? 'sorted-asc' : 'sorted-desc');
            }}
            render();
        }}

        function openM(id) {{
            const p = data.players.find(x => x.usta_id === id);
            if (!p) return;
            document.getElementById('mName').innerText = p.name + (p.usta_id ? ` (USTA ID: ${{p.usta_id}})` : '');
            document.getElementById('mList').innerHTML = (p.rankings || []).map(r => `
                <div class="modal-item">
                    <strong>${{r.displayLabel || 'Ranking'}}</strong><br>
                    National: #${{r.rank?.national || 'N/A'}} &bull; Section: #${{r.rank?.section || 'N/A'}} &bull; Points: ${{r.points ?? '-'}}
                </div>
            `).join('');
            document.getElementById('modal').style.display = 'flex';
        }}

        function closeM(e) {{
            if (!e || e.target.id === 'modal' || e.target.tagName === 'BUTTON') {{
                document.getElementById('modal').style.display = 'none';
            }}
        }}

        function exportCSV() {{
            const rows = data.players.map((p, i) => [i+1, `"${{p.name}}"`, p.utr_singles||'', p.utr_doubles||'', p.national_rank||'', p.section_rank||'', p.points||'', `"${{p.city||''}}"`, p.usta_id||'', p.is_tracked ? 'YES' : 'NO']);
            const csv = "Position,Name,UTR Singles,UTR Doubles,National Rank,Section Rank,Points,City,USTA ID,Tracked\\n" + rows.map(r => r.join(',')).join('\\n');
            const a = document.createElement('a');
            a.href = 'data:text/csv;charset=utf-8,' + encodeURI(csv);
            a.download = 'usta_standings.csv';
            a.click();
        }}

        document.getElementById('search').addEventListener('input', render);
        document.getElementById('statusFilter').addEventListener('change', render);
        render();
    </script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Fetch USTA tournament player rankings into an HTML dashboard.")
    parser.add_argument(
        "tournament",
        nargs="?",
        default="754482C7-13BA-4900-BE3B-FEE68EF50BE0",
        help="USTA Tournament URL or UUID (default: Princeton B/G 12s)",
    )
    parser.add_argument(
        "--list-name",
        "-l",
        default=None,
        help="Target ranking list or shortcut ('14', 'B14', 'G14', '12', '16', '18'; default: auto-detected from tournament title)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Path for generated HTML file (default: usta_rankings_<id>.html)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not automatically open HTML file in default web browser",
    )
    parser.add_argument(
        "--no-utr",
        action="store_true",
        help="Skip fetching UTR (Universal Tennis Rating) scores for players",
    )
    parser.add_argument(
        "--tracked",
        "-t",
        dest="tracked_file",
        default=None,
        help="Path to config file of tracked player names or USTA IDs (default: tracked_players.txt if present)",
    )

    args = parser.parse_args()

    try:
        t_id = extract_tournament_id(args.tournament)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\n🎾 Fetching tournament roster & player rankings for ID: {t_id}")

    # Load tracked players config if available
    tracked_set = load_tracked_players(args.tracked_file)
    if tracked_set:
        src = args.tracked_file or "tracked_players.txt"
        print(f"⭐ Loaded {len(tracked_set)} tracked player pattern(s) from '{src}'")

    def progress(curr, tot, name):
        pct = int((curr / tot) * 100) if tot else 0
        sys.stdout.write(f"\r[{('#' * (pct // 5)).ljust(20, '-')}] {pct}% ({curr}/{tot}) - {name[:25]:<25}")
        sys.stdout.flush()

    data = fetch_tournament_roster_with_rankings(
        t_id, max_workers=8, on_progress=progress, fetch_utr=not args.no_utr
    )
    print("\n")

    t_details = data.get("tournament") or {}
    players = data.get("players") or []
    t_name = t_details.get("name", "Unknown Tournament")

    target_list = resolve_target_list(args.list_name, t_name)

    print(f"✅ Loaded '{t_name}' with {len(players)} players.")
    print(f"🎯 Target List: '{target_list}'")

    html_content = generate_html(t_details, players, target_list, tracked_players=tracked_set)
    out_file = args.output or f"usta_rankings_{t_id}.html"
    abs_out = os.path.abspath(out_file)

    with open(abs_out, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"📄 Dashboard saved: {abs_out}")

    # Print summary
    processed = process_player_rankings(players, target_list, tracked_players=tracked_set)
    ranked = [p for p in processed if p["has_target_rank"]]
    print(f"🏆 Top 5 Players:")
    for idx, p in enumerate(ranked[:5], 1):
        star = "⭐ " if p.get("is_tracked") else "   "
        utr_str = f"UTR: {p['utr_singles_display']}" if p.get("utr_singles") else "UTR: -"
        print(f"  {star}{idx}. {p['name']:<22} | Nat. Rank: #{p['national_rank']:<5} | {utr_str:<10} | Pts: {p['points'] or 0:<4}")
    print(f"Total: {len(ranked)} ranked / {len(players)} players.\n")

    # If tracked players found in tournament, display them specifically
    tracked_matches = [p for p in processed if p.get("is_tracked")]
    if tracked_matches:
        print(f"⭐ Tracked Players in this Tournament ({len(tracked_matches)}):")
        for p in tracked_matches:
            n_rank = f"#{p['national_rank']}" if p.get("national_rank") else "Unranked"
            utr_str = f"UTR: {p['utr_singles_display']}" if p.get("utr_singles") else "UTR: -"
            pts_str = f"{p['points']} pts" if p.get("points") is not None else "- pts"
            print(f"   ★ {p['name']:<22} | Nat. Rank: {n_rank:<8} | {utr_str:<10} | {pts_str:<8} | ID: {p.get('usta_id') or 'N/A'}")
        print()

    if not args.no_browser:
        print(f"🌐 Opening dashboard in web browser...")
        webbrowser.open(f"file:///{abs_out}")


if __name__ == "__main__":
    main()

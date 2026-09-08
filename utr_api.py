#!/usr/bin/env python3
"""
UTR (Universal Tennis Rating) API Client
=========================================
Reverse-engineered public API client to query player profiles, UTR singles & doubles
ratings, reliability, and profile links from UTR Sports (app.utrsports.net).

Pure Python standard library (no pip packages required).
"""

import json
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

UTR_SEARCH_URL = "https://app.utrsports.net/api/v2/search/players?query="
UTR_PLAYER_V2_URL = "https://app.utrsports.net/api/v2/player/"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# In-memory cache to avoid duplicate network lookups during a session
_UTR_CACHE: Dict[str, Dict[str, Any]] = {}

# US State abbreviations mapping for location disambiguation
STATE_ABBR_TO_NAME = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas", "CA": "california",
    "CO": "colorado", "CT": "connecticut", "DE": "delaware", "FL": "florida", "GA": "georgia",
    "HI": "hawaii", "ID": "idaho", "IL": "illinois", "IN": "indiana", "IA": "iowa",
    "KS": "kansas", "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland",
    "MA": "massachusetts", "MI": "michigan", "MN": "minnesota", "MS": "mississippi",
    "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada", "NH": "new hampshire",
    "NJ": "new jersey", "NM": "new mexico", "NY": "new york", "NC": "north carolina",
    "ND": "north dakota", "OH": "ohio", "OK": "oklahoma", "OR": "oregon", "PA": "pennsylvania",
    "RI": "rhode island", "SC": "south carolina", "SD": "south dakota", "TN": "tennessee",
    "TX": "texas", "UT": "utah", "VT": "vermont", "VA": "virginia", "WA": "washington",
    "WV": "west virginia", "WI": "wisconsin", "WY": "wyoming"
}


def _normalize_location_text(city: Optional[str], state: Optional[str]) -> str:
    """Normalizes city and state text for fuzzy matching."""
    parts = []
    if city:
        parts.append(city.strip().lower())
    if state:
        st = state.strip().upper()
        parts.append(st.lower())
        if st in STATE_ABBR_TO_NAME:
            parts.append(STATE_ABBR_TO_NAME[st])
    return " ".join(parts)


def search_utr_player(
    name: str,
    city: Optional[str] = None,
    state: Optional[str] = None,
    timeout: int = 10,
) -> Optional[Dict[str, Any]]:
    """
    Searches UTR Sports directory for a player by name and selects the best candidate
    matching the optional city and state.
    """
    clean_name = name.strip()
    if not clean_name:
        return None

    encoded_query = urllib.parse.quote(clean_name)
    url = f"{UTR_SEARCH_URL}{encoded_query}"
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://app.utrsports.net/",
    }

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

    hits = data.get("hits") or []
    if not hits:
        return None

    norm_target_loc = _normalize_location_text(city, state)
    target_name_parts = [p.lower() for p in re.split(r"\s+", clean_name) if p]

    candidates = []
    for h in hits:
        source = h.get("source") or {}
        first = (source.get("firstName") or "").strip().lower()
        last = (source.get("lastName") or "").strip().lower()
        full = f"{first} {last}".strip()

        # Check name resemblance
        if not all(p in full for p in target_name_parts):
            # Check if at least last name matches
            if target_name_parts and target_name_parts[-1] != last:
                continue

        pid = str(h.get("id") or "").strip()
        loc_display = ((source.get("location") or {}).get("display") or "").strip()
        candidates.append({
            "id": pid,
            "name": f"{source.get('firstName', '')} {source.get('lastName', '')}".strip(),
            "location": loc_display,
            "age": source.get("age"),
            "gender": source.get("gender"),
        })

    if not candidates:
        # Fallback to the very first hit if name starts similarly
        first_hit = hits[0].get("source") or {}
        pid = str(hits[0].get("id") or "").strip()
        return {
            "id": pid,
            "name": f"{first_hit.get('firstName', '')} {first_hit.get('lastName', '')}".strip(),
            "location": ((first_hit.get("location") or {}).get("display") or "").strip(),
            "age": first_hit.get("age"),
        }

    # If location info was provided, score candidates by location match
    if norm_target_loc:
        best_candidate = None
        best_score = -1
        for c in candidates:
            c_loc = (c.get("location") or "").lower()
            score = 0
            if city and city.lower() in c_loc:
                score += 3
            if state:
                st_upper = state.upper()
                st_full = STATE_ABBR_TO_NAME.get(st_upper, "")
                if st_upper in c_loc.upper().split() or (st_full and st_full in c_loc):
                    score += 2
            if score > best_score:
                best_score = score
                best_candidate = c
        if best_candidate and best_score > 0:
            return best_candidate

    return candidates[0]


def fetch_player_utr_details(utr_id: str, timeout: int = 10) -> Dict[str, Any]:
    """
    Fetches exact two-decimal UTR ratings, status, reliability, and profile URL
    from UTR Sports API v2.
    """
    clean_id = str(utr_id).strip()
    if not clean_id:
        return {}

    url = f"{UTR_PLAYER_V2_URL}{clean_id}"
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Referer": f"https://app.utrsports.net/profiles/{clean_id}",
    }

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}

    singles_disp = data.get("singlesUtrDisplay") or str(data.get("singlesUtr") or "")
    doubles_disp = data.get("doublesUtrDisplay") or str(data.get("doublesUtr") or "")
    singles_float = data.get("singlesUtr")
    doubles_float = data.get("doublesUtr")

    try:
        singles_val = float(singles_disp) if singles_disp else (float(singles_float) if singles_float else None)
    except (ValueError, TypeError):
        singles_val = None

    try:
        doubles_val = float(doubles_disp) if doubles_disp else (float(doubles_float) if doubles_float else None)
    except (ValueError, TypeError):
        doubles_val = None

    loc_obj = data.get("location") or {}
    loc_display = loc_obj.get("display") or ""
    if not loc_display and (loc_obj.get("cityName") or loc_obj.get("stateName")):
        loc_display = f"{loc_obj.get('cityName', '')}, {loc_obj.get('stateName', '')}".strip(", ")

    return {
        "utr_id": clean_id,
        "singles_utr": singles_val,
        "singles_utr_display": singles_disp if singles_disp != "0.00" else "Unrated",
        "doubles_utr": doubles_val,
        "doubles_utr_display": doubles_disp if doubles_disp != "0.00" else "Unrated",
        "singles_reliability": data.get("ratingProgressSingles"),
        "doubles_reliability": data.get("ratingProgressDoubles"),
        "profile_url": f"https://app.utrsports.net/profiles/{clean_id}",
        "location": loc_display,
        "age": data.get("age"),
    }


def get_player_utr(
    name: str,
    city: Optional[str] = None,
    state: Optional[str] = None,
    timeout: int = 10,
) -> Dict[str, Any]:
    """
    High-level convenience method: Searches for a player and retrieves their full UTR rating.
    Results are cached in-memory by normalized name and location.
    """
    cache_key = f"{name.strip().lower()}|{(city or '').strip().lower()}|{(state or '').strip().lower()}"
    if cache_key in _UTR_CACHE:
        return _UTR_CACHE[cache_key]

    match = search_utr_player(name, city=city, state=state, timeout=timeout)
    if not match or not match.get("id"):
        result = {}
    else:
        result = fetch_player_utr_details(match["id"], timeout=timeout)

    _UTR_CACHE[cache_key] = result
    return result


if __name__ == "__main__":
    import sys
    test_player = sys.argv[1] if len(sys.argv) > 1 else "Austin He"
    print(f"[*] Testing UTR lookup for: {test_player}...")
    utr_data = get_player_utr(test_player)
    print(json.dumps(utr_data, indent=2))

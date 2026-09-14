# USTA Tournament Standings & Rankings Generator

A standalone Python utility that extracts tournament player rosters from USTA (`playtennis.usta.com`), automatically retrieves each player's official USTA National Standings & Rankings (e.g., **"Boys' 12 National Standings List (combined)"**), and queries live **UTR (Universal Tennis Rating)** singles and doubles scores directly from UTR Sports.

---

## Features

- **Zero Dependencies**: Uses only standard Python 3 (`urllib`, `json`, `hmac`, `hashlib`, `webbrowser`). No `pip install` or external packages required.
- **Direct API Integration**: Reverse-engineers USTA's Clubspark GraphQL endpoint and player ranking APIs (with HMAC-SHA256 authentication) to pull rosters and standings in seconds.
- **Live UTR Rating Integration**: Concurrently queries Universal Tennis Rating (UTR singles and doubles, two-decimal accuracy) with geographic location disambiguation.
- **Tracked Players Config & Highlighted Border**: Provide a `tracked_players.txt` file (one player name or UAID per line); matching players are highlighted with a prominent gold border and badge in the interactive dashboard, included in a "Tracked Only" filter, and marked in console output.
- **Multiple Input Formats Supported**:
  - Full Tournament URL (e.g. `https://playtennis.usta.com/.../players/<id>`)
  - Public USTA Sanction Tournament ID (e.g. `26-17452`, automatically resolved via search API)
  - Tournament database UUID (e.g. `754482C7-13BA-4900-BE3B-FEE68EF50BE0`)
- **Self-Contained Interactive HTML Dashboard**:
  - **Live Search & Tracked Filter**: Instant filtering by player name, city, state, or filter to "Tracked Only".
  - **Highlighted Player Row**: Tracked players feature a prominent glowing amber border encircling the whole row and a ⭐ icon next to their name.
  - **Two-Way Column Sorting**: Sort by UTR, National Rank, Section Rank, Points, Match Record (W/L), Name, etc.
  - **All-Rankings Modal**: Click on any player to see all ranking lists they hold (Quota, Seeding, other age divisions).
  - **Direct Profile Links**: One-click links directly to each player's official USTA profile page and UTR profile.
  - **CSV Export**: Export the ranked tournament roster (including UTR ratings and Tracked status) to CSV with a single click.
  - **Automatic Browser Launch**: Automatically opens the generated dashboard in your default browser.

---

## Quick Start

### 1. Run the default sample tournament (fetches USTA rankings + UTR scores):
```bash
python usta_rankings.py
```

### 2. Track specific players via config file:
Create `tracked_players.txt` in the folder (or use `--tracked <file>`) with one name or UAID per line:
```text
# tracked_players.txt
2019333897
Austin He
Shlok Donga
```
Run as normal:
```bash
python usta_rankings.py 26-17452
```
Matching players will have a prominent highlighted border in the HTML dashboard and be marked with `⭐` in the terminal.

### 3. Run with any tournament URL:
```bash
python usta_rankings.py "https://playtennis.usta.com/Competitions/princetontennisprogram/Tournaments/players/754482C7-13BA-4900-BE3B-FEE68EF50BE0"
```

### 4. Run with a USTA Sanction Tournament ID directly:
```bash
python usta_rankings.py 26-17452
```

### 5. Check a different age division (Auto-detected or via Shortcuts):
The script automatically detects the division from the tournament title (e.g. `14s`, `12s`, `16s`). You can also use convenient shortcuts with `-l`:
```bash
# Auto-detects 14U from tournament title:
python usta_rankings.py "https://playtennis.usta.com/Competitions/teamsharkattacktennis/Tournaments/players/C7A7F321-7188-4EA0-9936-A76B3BE18854"

# Use shortcuts: 14, B14, G14, 12, B12, G12, 16, B16, G16, 18, B18, G18
python usta_rankings.py <tournament> -l 14
python usta_rankings.py <tournament> -l G14
```

### 6. Skip UTR lookup to speed up execution:
```bash
python usta_rankings.py 26-17452 --no-utr
```

---

## CLI Options

| Argument / Flag | Description | Default |
|-----------------|-------------|---------|
| `tournament` | Tournament URL, UUID, or Sanction ID (e.g. `26-17452`) | Default tournament |
| `--list-name`, `-l` | Target ranking list name or shortcut (`14`, `B14`, `G14`, etc.) | Auto-detected from title (fallback: Boys' 12) |
| `--output`, `-o` | Custom output HTML filename | `usta_rankings_<id>.html` |
| `--tracked`, `-t` | Path to text config file of tracked players | `tracked_players.txt` (if present) |
| `--no-browser` | Generate HTML file without auto-opening in browser | `False` |
| `--no-utr` | Skip fetching UTR scores for players | `False` |

---

## Standalone UTR API Client (`utr_api.py`)

You can also use the included `utr_api.py` module independently to look up any player's UTR score directly from the command line:

```bash
python utr_api.py "Austin He"
```

Output:
```json
{
  "utr_id": "3167191",
  "singles_utr": 6.3,
  "singles_utr_display": "6.30",
  "doubles_utr": 6.44,
  "doubles_utr_display": "6.44",
  "singles_reliability": 100,
  "doubles_reliability": 100,
  "profile_url": "https://app.utrsports.net/profiles/3167191",
  "location": "West Chester, PA",
  "age": 13
}
```

---

## License
MIT License

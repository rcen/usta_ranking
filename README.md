# USTA Tournament Standings & Rankings Generator

A standalone Python utility that extracts tournament player rosters from USTA (`playtennis.usta.com`), automatically retrieves each player's official USTA National Standings & Rankings (e.g., **"Boys' 12 National Standings List (combined)"**), and queries live **UTR (Universal Tennis Rating)** singles and doubles scores directly from UTR Sports.

---

## Features

- **Zero Dependencies**: Uses only standard Python 3 (`urllib`, `json`, `hmac`, `hashlib`, `webbrowser`). No `pip install` or external packages required.
- **Direct API Integration**: Reverse-engineers USTA's Clubspark GraphQL endpoint and player ranking APIs (with HMAC-SHA256 authentication) to pull rosters and standings in seconds.
- **Live UTR Rating Integration**: Concurrently queries Universal Tennis Rating (UTR singles and doubles, two-decimal accuracy) with geographic location disambiguation.
- **Multiple Input Formats Supported**:
  - Full Tournament URL (e.g. `https://playtennis.usta.com/.../players/<id>`)
  - Public USTA Sanction Tournament ID (e.g. `26-17452`, automatically resolved via search API)
  - Tournament database UUID (e.g. `754482C7-13BA-4900-BE3B-FEE68EF50BE0`)
- **Self-Contained Interactive HTML Dashboard**:
  - **Live Search**: Instant filtering by player name, city, or state.
  - **Two-Way Column Sorting**: Sort by National Rank, Section Rank, Points, UTR Singles, UTR Doubles, Match Record (W/L), Name, etc.
  - **All-Rankings Modal**: Click on any player to see all ranking lists they hold (Quota, Seeding, other age divisions).
  - **Direct Profile Links**: One-click links directly to each player's official USTA profile page and UTR profile.
  - **CSV Export**: Export the ranked tournament roster (including UTR ratings) to CSV with a single click.
  - **Automatic Browser Launch**: Automatically opens the generated dashboard in your default browser.

---

## Quick Start

### 1. Run the default sample tournament (fetches USTA rankings + UTR scores):
```bash
python usta_rankings.py
```

### 2. Run with any tournament URL:
```bash
python usta_rankings.py "https://playtennis.usta.com/Competitions/princetontennisprogram/Tournaments/players/754482C7-13BA-4900-BE3B-FEE68EF50BE0"
```

### 3. Run with a USTA Sanction Tournament ID directly:
```bash
python usta_rankings.py 26-17452
```

### 4. Check a different age division (e.g. Boys' 14 or Girls' 12):
```bash
python usta_rankings.py 26-17452 --list-name "Boys' 14 National Standings List (combined)"
```

### 5. Skip UTR lookup to speed up execution:
```bash
python usta_rankings.py 26-17452 --no-utr
```

---

## CLI Options

| Argument / Flag | Description | Default |
|-----------------|-------------|---------|
| `tournament` | Tournament URL, UUID, or Sanction ID (e.g. `26-17452`) | Default tournament |
| `--list-name`, `-l` | Target ranking list name to match | `"Boys' 12 National Standings List (combined)"` |
| `--output`, `-o` | Custom output HTML filename | `usta_rankings_<id>.html` |
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

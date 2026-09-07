# USTA Tournament Standings & Rankings Generator

A standalone, single-file Python utility that extracts tournament player rosters from USTA (`playtennis.usta.com`) and automatically retrieves each player's official USTA National Standings & Rankings (e.g., **"Boys' 12 National Standings List (combined)"**).

---

## Features

- **Single-File & Zero Dependencies**: Everything is contained inside `usta_rankings.py`. Uses only standard Python 3 (`urllib`, `json`, `hmac`, `hashlib`, `webbrowser`). No `pip install` or external packages required.
- **Direct API Integration**: Reverse-engineers USTA's Clubspark GraphQL endpoint and player ranking APIs (with HMAC-SHA256 authentication) to pull rosters and standings in seconds.
- **Multiple Input Formats Supported**:
  - Full Tournament URL (e.g. `https://playtennis.usta.com/.../players/<id>`)
  - Public USTA Sanction Tournament ID (e.g. `26-17452`, automatically resolved via search API)
  - Tournament database UUID (e.g. `754482C7-13BA-4900-BE3B-FEE68EF50BE0`)
- **Self-Contained Interactive HTML Dashboard**:
  - **Live Search**: Instant filtering by player name, city, state, or section.
  - **Two-Way Column Sorting**: Sort by National Rank, Section Rank, District Rank, Points, Match Record (W/L), Name, etc.
  - **All-Rankings Modal**: Click on any player to see all ranking lists they hold (Quota, Seeding, other age divisions).
  - **Direct Profile Links**: One-click links directly to each player's official USTA profile page.
  - **CSV Export**: Export the ranked tournament roster to CSV with a single click.
  - **Automatic Browser Launch**: Automatically opens the generated dashboard in your default browser.

---

## Quick Start

### 1. Run the default sample tournament:
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

---

## CLI Options

| Argument / Flag | Description | Default |
|-----------------|-------------|---------|
| `tournament` | Tournament URL, UUID, or Sanction ID (e.g. `26-17452`) | Default tournament |
| `--list-name`, `-l` | Target ranking list name to match | `"Boys' 12 National Standings List (combined)"` |
| `--output`, `-o` | Custom output HTML filename | `usta_rankings_<id>.html` |
| `--no-browser` | Generate HTML file without auto-opening in browser | `False` |

---

## License
MIT License

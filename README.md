# ECHOMARK Intel Portal — Python/Flask

A full-stack OSINT intelligence portal rebuilt from TypeScript/Express/React into Python/Flask with a vanilla JS single-page frontend.

## Stack

| Layer | TypeScript (original) | Python (this version) |
|---|---|---|
| Server | Express.js | Flask |
| Frontend | React + Vite + Tailwind | Vanilla JS + CSS vars (single HTML file) |
| Auth | JWT (jsonwebtoken) | JWT (PyJWT) |
| Storage | Local JSON + Firebase fallback | Local JSON files |
| OSINT pipeline | Async workers (Node) | Threading (Python) |
| Image forensics | Google Gemini SDK | Gemini REST API |

## Project Structure

```
echomark/
├── app.py                        # Flask app factory & entry point
├── requirements.txt
├── .env.example
├── case_data/                    # JSON storage for cases + users
│   ├── DCase1.json
│   └── ...
├── templates/
│   └── index.html                # Complete SPA frontend
└── server/
    ├── routes/
    │   ├── auth.py               # /api/auth (login, register, me)
    │   ├── cases.py              # /api/cases (CRUD + OSINT trigger)
    │   └── intel.py              # /api/active-scrape, analyze-image
    ├── storage/
    │   ├── users.py              # User JSON storage
    │   └── cases.py              # Case JSON storage
    └── services/osint/
        ├── pipeline.py           # OSINT orchestrator
        ├── facebook.py
        ├── instagram.py
        ├── twitter.py
        ├── phone.py
        ├── email.py
        ├── website.py
        ├── username.py           # Sherlock-style live HTTP probing
        ├── summary.py            # Sentiment, analytics, AI summary
        └── utils.py
```

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY if you want image forensics

# Run the server
python app.py
# Server starts at http://localhost:3000
```

## Default Login

| Field | Value |
|---|---|
| Operator ID | `admin` |
| Password | `admin` |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/login` | Login with operatorId + accessCode |
| POST | `/api/auth/register` | Register new operator |
| GET | `/api/auth/me` | Get current operator (JWT required) |
| GET | `/api/cases` | List all cases |
| POST | `/api/cases` | Create new case |
| GET | `/api/cases/<code>` | Get case by code |
| POST | `/api/cases/<code>/update-log` | Append a log entry |
| DELETE | `/api/cases/<code>` | Delete a case |
| POST | `/api/cases/<code>/trigger-osint` | Run OSINT pipeline (background) |
| POST | `/api/active-scrape` | Live scrape (url/domain/email) |
| POST | `/api/cases/<code>/analyze-image` | Gemini visual forensics |

## Frontend

The entire frontend is a single `templates/index.html` with no build step — vanilla JS handles routing, state, polling, and rendering. All CSS uses CSS custom properties matching the original Tailwind design tokens exactly (dark cyber theme, same colors, fonts, layout).

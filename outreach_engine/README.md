# Outreach Engine

Intent-first prospecting engine for finding businesses with visible buying signals, researching them, scoring fit, and creating Gmail drafts or sending qualified outreach.

## What it does

1. Searches the public web for configurable pain/buying signals.
2. Resolves the likely company website.
3. Crawls public pages such as home, about, contact and careers.
4. Extracts publicly listed business emails.
5. Uses Gemini when available to score fit and write a short personalized email.
6. Saves every lead and evidence item in SQLite.
7. Creates Gmail drafts by default. Auto-send is opt-in.

## Cost profile

The default stack uses free/open components:

- `ddgs` for search discovery
- direct public-page crawling with `httpx` + BeautifulSoup
- Gemini API free tier when available; deterministic fallback if no API key is present
- Gmail API for drafts/sending
- SQLite for storage

No paid enrichment provider is required for v1. This means the engine only uses contact details it can find publicly; it does not promise a verified direct email for every prospect.

## Safety defaults

- `send_mode: draft`
- daily draft/send cap
- duplicate suppression
- blacklist/suppression table
- evidence URL stored for every lead
- no outreach if no public business email is found
- optional opt-out footer

## Setup

```powershell
cd outreach_engine
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy config.example.yaml config.yaml
copy .env.example .env
python main.py --discover
```

For AI scoring/drafting, put a Gemini API key in `.env`.

For Gmail, create a Google Cloud OAuth Desktop App credential, enable Gmail API, download it as `credentials.json` into this folder, then run:

```powershell
python main.py --gmail-auth
```

The first run opens Google's OAuth consent page and writes `token.json` locally.

## Typical workflow

```powershell
# Find and qualify leads; save to DB
python main.py --discover

# Create Gmail drafts for qualified leads
python main.py --outreach

# Show today's pipeline stats
python main.py --stats
```

To enable sending, change `send_mode` in `config.yaml` from `draft` to `send`. Keep the daily cap conservative until the account/domain has a stable sending reputation.

## Configure your offer

The important section is `signals` in `config.yaml`. A signal is observable evidence that a business may need your service.

Example for an AI receptionist offer:

- hiring a receptionist/front-desk employee
- reviews mentioning unanswered calls or slow response
- no after-hours contact handling
- no online booking

Example for web design:

- visibly broken/mobile-unfriendly site
- missing HTTPS or dead pages
- old technology / poor conversion path
- recent rebrand/new location with stale site

The engine should hunt for evidence, not simply scrape a generic company list.

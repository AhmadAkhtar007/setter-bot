# Outreach Engine

Intent-first prospecting engine for finding businesses with visible buying signals, researching them, AI-qualifying the evidence, and creating personalized Gmail drafts or sending qualified outreach.

## Pipeline

```text
Web signal search
    -> business website research
    -> public contact discovery
    -> Gemini qualification
    -> pain + evidence score
    -> personalized email
    -> Gmail draft (default)
    -> optional send
```

## What the AI agent does

For every researched prospect, Gemini receives the detected signal, search evidence, company website text and your offer. It must decide:

- whether the prospect actually appears to have a relevant problem
- an evidence-based qualification score from 0-100
- confidence in the evidence
- the specific pain/need detected
- why your offer fits
- the shortest useful evidence fragment

Weak or ambiguous prospects are rejected before outreach. Qualified prospects then get a separate AI-written email based only on the stored evidence.

The prompt explicitly forbids invented pain, fake compliments, fake personal experience, fabricated company facts and unsupported claims.

## Files

- `main.py` - original deterministic crawler/Gmail core
- `ai_agent.py` - Gemini qualification + email-writing agent
- `smart_main.py` - recommended entrypoint; connects AI to discovery and outreach
- `config.example.yaml` - offer, ICP, signal, qualification and volume settings
- `.env.example` - API/OAuth environment variables
- `leads.db` - generated SQLite lead/evidence database

## Cost profile

Default stack:

- DDGS for search discovery
- `httpx` + BeautifulSoup for direct public-page research
- Gemini API for qualification/personalization when a key is configured
- Gmail API for draft/send
- SQLite for local storage

There is no required paid lead database or enrichment provider in v1. This also means the engine only uses contact details it can find publicly and cannot guarantee a direct verified decision-maker email for every company.

## Safe defaults

- `send_mode: draft`
- daily cap: 25
- AI minimum qualification score: 50
- AI minimum evidence confidence: 55%
- duplicate suppression
- opt-out footer
- no outreach when no public email is available
- evidence stored with every qualified lead

## Setup

```powershell
cd outreach_engine
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy config.example.yaml config.yaml
copy .env.example .env
```

Put your Gemini API key in `.env`:

```text
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.5-flash-lite
```

Then edit `config.yaml` with your actual offer, industries, countries and buying/pain signals.

## Gmail OAuth

Create a Google Cloud OAuth Desktop App credential, enable Gmail API, and download the credential file into this folder as `credentials.json`.

Then run:

```powershell
python smart_main.py --gmail-auth
```

The first authentication opens Google's OAuth screen and creates a local `token.json`.

Do not commit `credentials.json`, `token.json`, `.env`, or `leads.db`.

## Run

### 1. Find + research + qualify leads

```powershell
python smart_main.py --discover
```

The engine searches configured signals, crawls each candidate business, rejects weak leads and stores qualified prospects in SQLite.

### 2. Create personalized Gmail drafts

```powershell
python smart_main.py --outreach
```

Default configuration creates Gmail drafts only.

### 3. See pipeline counts

```powershell
python smart_main.py --stats
```

### Run the full pipeline

```powershell
python smart_main.py --all
```

## Enable auto-send

Only after reviewing draft quality, change:

```yaml
outreach:
  send_mode: send
```

Keep a conservative daily cap while the mailbox/domain establishes a stable sending reputation.

## Configure buying signals

The most important part of the system is the `signals` section. A signal is observable evidence that a business may need the offer.

For an AI receptionist offer, useful signals can include:

- hiring a receptionist/front-desk employee
- public complaints about unanswered calls
- phone-only appointment scheduling
- after-hours contact gaps

For web design, useful signals can include:

- broken/mobile-unfriendly pages
- dead conversion paths
- stale site after a rebrand or new location
- missing/poor booking or lead-capture flow

The engine is intentionally designed to hunt evidence first instead of scraping a generic company list and pretending every company is a lead.

# Outreach Engine

Intent-first prospecting engine for finding businesses with visible buying signals, researching them, identifying the best public contact, AI-qualifying the evidence, and creating personalized Gmail drafts or sending qualified outreach.

## Pipeline

```text
Web signal search
    -> business website research
    -> decision-maker/contact intelligence
    -> public email + MX validation
    -> Gemini qualification
    -> pain + evidence score
    -> personalized email
    -> Gmail draft (default)
    -> optional send
```

## What the contact intelligence agent does

For each candidate business it:

- searches public web evidence for owners, founders, CEOs, partners, principals and managers
- scans the company's public website for names, titles and business emails
- keeps only publicly observed emails; it does not fabricate `firstname@company.com` guesses
- prefers the prospect's own domain over unrelated third-party addresses
- checks whether the email domain has MX records
- ranks named contacts and role inboxes by confidence
- records the contact source URL and evidence
- distinguishes a true name-email match from a generic company inbox

If the engine finds a decision-maker name but cannot directly link that name to the email address, it may still use the public business inbox, but it will **not** write a named greeting such as `Hi John,` to `info@company.com`.

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

- `main.py` - deterministic crawler/Gmail core
- `contact_agent.py` - public decision-maker/contact discovery + MX validation
- `ai_agent.py` - Gemini qualification + email-writing agent
- `smart_main.py` - recommended entrypoint; connects contact intelligence, AI and Gmail
- `config.example.yaml` - offer, ICP, signal, qualification, contact and volume settings
- `.env.example` - API/OAuth environment variables
- `leads.db` - generated SQLite lead/evidence database

## Cost profile

Default stack:

- DDGS for public search discovery
- `httpx` + BeautifulSoup for direct public-page research
- `dnspython` for email-domain MX checks
- Gemini API for qualification/personalization when a key is configured
- Gmail API for draft/send
- SQLite for local storage

There is no required paid lead database or enrichment provider in v1. That keeps the stack cheap, but coverage is intentionally lower than paid enrichment systems: if a trustworthy public contact cannot be found, the lead is skipped.

## Safe defaults

- `send_mode: draft`
- daily cap: 25
- AI minimum qualification score: 50
- AI minimum evidence confidence: 55%
- contact confidence threshold: 45
- duplicate suppression
- opt-out footer
- no outreach when no sufficiently supported public email is available
- named greeting only for direct name-email matches
- evidence and contact source stored with every qualified lead

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

### 1. Find + research + contact-enrich + qualify leads

```powershell
python smart_main.py --discover
```

The engine searches configured signals, researches each business, finds the strongest public contact, rejects weak leads and stores qualified prospects in SQLite.

### 2. Create personalized Gmail drafts

```powershell
python smart_main.py --outreach
```

Default configuration creates Gmail drafts only.

### 3. See pipeline counts

```powershell
python smart_main.py --stats
```

Stats now include AI-qualified leads, named decision-makers found, direct name-email matches and MX-valid emails.

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

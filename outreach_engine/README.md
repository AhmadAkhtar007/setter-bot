# Outreach Engine

Intent-first prospecting engine for finding businesses with visible buying signals, researching them, identifying a public contact, AI-qualifying the evidence, and creating personalized Gmail drafts.

## Pipeline

```text
Web signal search
    -> business website research
    -> public contact discovery
    -> AI qualification
    -> personalized email
    -> Gmail draft (default)
```

## LLM providers

The AI layer uses one OpenAI-compatible adapter. No provider-specific SDK is required.

Default order:

```text
NVIDIA NIM -> OpenRouter -> Gemini
```

If NVIDIA errors, rate-limits, times out, or returns malformed/wrong-schema JSON, the same request is retried on OpenRouter. If OpenRouter also fails, Gemini is tried.

Default endpoints/models:

- NVIDIA: `https://integrate.api.nvidia.com/v1` using `nvidia/llama-3.3-nemotron-super-49b-v1.5`
- OpenRouter: `https://openrouter.ai/api/v1` using `openrouter/free`
- Gemini: `https://generativelanguage.googleapis.com/v1beta/openai/` using `gemini-3.8-flash`

Models can be changed only through `.env`; the application code stays the same.

## Setup

```powershell
cd outreach_engine
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy config.example.yaml config.yaml
copy .env.example .env
```

Add whichever provider keys you have to `.env`:

```text
NVIDIA_API_KEY=your_nvidia_key
NVIDIA_MODEL=nvidia/llama-3.3-nemotron-super-49b-v1.5

OPENROUTER_API_KEY=your_openrouter_key
OPENROUTER_MODEL=openrouter/free

GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-3.8-flash
```

You do not need all three. Missing providers are skipped automatically.

Provider priority is controlled in `config.yaml`:

```yaml
ai:
  enabled: true
  provider_order: ["nvidia", "openrouter", "gemini"]
```

## What the AI does

For every researched prospect, the model receives the detected signal, public evidence, relevant website text and your offer. It decides whether there is enough observable evidence to justify outreach and returns strict JSON.

The output is schema-validated. A provider does not count as successful merely because it returned HTTP 200; malformed JSON or the wrong fields trigger fallback to the next provider.

Qualified prospects then get a short evidence-based email. Prompts explicitly forbid invented pain, fake compliments, fabricated company facts and unsupported claims.

## Contact intelligence

For each candidate business the engine can:

- search public web evidence for owners/founders/managers
- scan the business website for public emails
- avoid fabricated `firstname@company.com` guesses
- prefer the prospect's own domain
- check MX records
- use a named greeting only when the name-email link is sufficiently supported

## Files

- `main.py` - crawler/Gmail core
- `contact_agent.py` - public contact discovery
- `ai_agent.py` - provider adapter + qualification + email writing
- `smart_main.py` - recommended entrypoint
- `config.example.yaml` - offer, ICP, signal and provider-order settings
- `.env.example` - API/OAuth variables

## Gmail OAuth

Create a Google Cloud OAuth Desktop App credential, enable Gmail API, and save the credential file here as `credentials.json`.

Then run:

```powershell
python smart_main.py --gmail-auth
```

The first authentication creates a local `token.json`.

Do not commit `credentials.json`, `token.json`, `.env`, `config.yaml`, or `leads.db`.

## Run

Find + research + qualify leads:

```powershell
python smart_main.py --discover
```

Create personalized Gmail drafts:

```powershell
python smart_main.py --outreach
```

Show pipeline counts:

```powershell
python smart_main.py --stats
```

Run discovery then outreach:

```powershell
python smart_main.py --all
```

Default `send_mode` is `draft`. Only switch it to `send` after reviewing real draft quality.

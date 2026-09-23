from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field


class QualificationResult(BaseModel):
    qualified: bool
    score: int = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=100)
    pain_summary: str
    reason: str
    evidence_quote: str


class EmailResult(BaseModel):
    subject: str
    body: str


@dataclass
class AgentResult:
    qualified: bool
    score: int
    confidence: int
    pain_summary: str
    reason: str
    evidence_quote: str


def _client_and_model(config: dict):
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None, None
    model = (
        config.get("ai", {}).get("model")
        or os.getenv("GEMINI_MODEL")
        or "gemini-3.5-flash-lite"
    )
    return genai.Client(api_key=api_key), model


def available(config: dict) -> bool:
    if not config.get("ai", {}).get("enabled", True):
        return False
    client, _ = _client_and_model(config)
    return client is not None


def qualify_lead(*, company: str, website: str, signal_name: str, signal_score: int,
                 evidence_url: str, evidence_text: str, research_text: str,
                 config: dict) -> AgentResult | None:
    client, model = _client_and_model(config)
    if client is None:
        return None

    offer = config.get("offer", {})
    target = config.get("target", {})
    prompt = f"""
You are a strict B2B prospect qualification analyst.

Goal: decide whether this business has OBSERVABLE evidence of a problem that the offer can plausibly solve.
Do not infer a pain merely because the company belongs to a target industry.
Do not invent facts, people, revenue, tools, call volume, or operational problems.
If evidence is weak/ambiguous, mark qualified=false.

OFFER
Name: {offer.get('name', '')}
Description: {offer.get('description', '')}
Target industries: {', '.join(target.get('industries', []))}
Target countries: {', '.join(target.get('countries', []))}

PROSPECT
Company: {company}
Website: {website}
Detected signal: {signal_name}
Heuristic signal score: {signal_score}/100
Evidence URL: {evidence_url}
Search evidence: {evidence_text[:3000]}
Website research: {research_text[:14000]}

Scoring rubric:
0-29: no useful evidence / likely irrelevant
30-49: weak but plausible signal
50-69: clear problem signal and reasonable offer fit
70-84: strong recent/direct need signal
85-100: unusually explicit buying/need signal

Return:
- qualified: only true if contacting them is justified by evidence
- score: 0-100
- confidence: confidence in the evidence, not confidence that they will buy
- pain_summary: one factual sentence, no hype
- reason: concise explanation tying evidence to the offer
- evidence_quote: the shortest useful exact fragment from supplied evidence; empty if none
"""

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=QualificationResult,
                temperature=0.1,
            ),
        )
        parsed = response.parsed
        if not parsed:
            return None
        return AgentResult(
            qualified=bool(parsed.qualified),
            score=int(parsed.score),
            confidence=int(parsed.confidence),
            pain_summary=parsed.pain_summary.strip(),
            reason=parsed.reason.strip(),
            evidence_quote=parsed.evidence_quote.strip(),
        )
    except Exception as exc:
        print(f"[ai-qualification-error] {company}: {exc}")
        return None


def write_email(*, company: str, signal_name: str, evidence_text: str,
                pain_summary: str, ai_reason: str, config: dict) -> tuple[str, str] | None:
    client, model = _client_and_model(config)
    if client is None:
        return None

    offer = config.get("offer", {})
    outreach = config.get("outreach", {})
    max_words = int(config.get("ai", {}).get("max_email_words", 90))

    prompt = f"""
Write a concise, human B2B cold email based ONLY on the evidence below.

Rules:
- Do not invent or exaggerate facts.
- Never pretend you personally experienced their service.
- Do not use fake compliments.
- Do not say "I noticed" unless the supplied evidence actually supports the statement.
- Lead with the specific business signal/problem, not with the sender.
- Connect that signal to the offer in plain English.
- No buzzwords, em dashes, hype, or fake urgency.
- One low-friction CTA.
- Keep the BODY under {max_words} words, excluding signature/opt-out.
- Do not add an opt-out sentence; the sending layer handles it.
- Subject should be 2-6 words and not clickbait.

PROSPECT
Company: {company}
Signal: {signal_name}
Evidence: {evidence_text[:3500]}
Validated pain: {pain_summary}
Qualification reasoning: {ai_reason}

OFFER
Name: {offer.get('name', '')}
What it does: {offer.get('description', '')}
CTA preference: {offer.get('cta', 'Open to a quick chat?')}
Sender name: {offer.get('sender_name', '')}

Write as a competent operator, not a marketing copywriter.
Return subject and body. The body should begin with "Hi," and end with the sender name.
"""

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=EmailResult,
                temperature=0.35,
            ),
        )
        parsed = response.parsed
        if not parsed:
            return None
        subject = parsed.subject.strip().replace("\n", " ")[:120]
        body = parsed.body.strip()
        if not subject or not body:
            return None
        return subject, body
    except Exception as exc:
        print(f"[ai-email-error] {company}: {exc}")
        return None

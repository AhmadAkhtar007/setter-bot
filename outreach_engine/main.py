from __future__ import annotations

import argparse
import base64
import email.utils
import hashlib
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import httpx
import yaml
from bs4 import BeautifulSoup
from ddgs import DDGS
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "leads.db"
CONFIG_PATH = ROOT / "config.yaml"
SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
COMMON_FREE_EMAILS = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com", "aol.com"}
SKIP_HOSTS = {
    "linkedin.com", "www.linkedin.com", "facebook.com", "www.facebook.com", "instagram.com", "www.instagram.com",
    "indeed.com", "www.indeed.com", "glassdoor.com", "www.glassdoor.com", "yelp.com", "www.yelp.com",
    "yellowpages.com", "www.yellowpages.com", "mapquest.com", "www.mapquest.com", "reddit.com", "www.reddit.com",
}


@dataclass
class Candidate:
    company: str
    website: str
    signal_name: str
    signal_score: int
    evidence_url: str
    evidence_text: str
    email: str | None = None
    score: int = 0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise SystemExit("Missing config.yaml. Copy config.example.yaml to config.yaml and edit it first.")
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT UNIQUE NOT NULL,
            company TEXT NOT NULL,
            website TEXT NOT NULL,
            email TEXT,
            signal_name TEXT NOT NULL,
            signal_score INTEGER NOT NULL,
            score INTEGER NOT NULL,
            evidence_url TEXT NOT NULL,
            evidence_text TEXT,
            status TEXT NOT NULL DEFAULT 'discovered',
            subject TEXT,
            body TEXT,
            gmail_message_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS suppressions (
            email TEXT PRIMARY KEY,
            reason TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def normalize_url(url: str) -> str:
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path or '/'}"


def root_url(url: str) -> str:
    p = urlparse(normalize_url(url))
    return f"{p.scheme}://{p.netloc}/"


def company_from_result(title: str, url: str) -> str:
    title = re.sub(r"\s+[|\-–—:]\s+.*$", "", title or "").strip()
    if 2 <= len(title) <= 80:
        return title
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return host.split(".")[0].replace("-", " ").title()


def fingerprint(company: str, website: str, email_addr: str | None) -> str:
    raw = f"{company.lower().strip()}|{root_url(website).lower()}|{(email_addr or '').lower().strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def search_candidates(config: dict) -> list[Candidate]:
    target = config["target"]
    max_results = int(target.get("max_search_results_per_query", 20))
    countries = target.get("countries", [""])
    industries = target.get("industries", [])
    signals = config.get("signals", [])
    found: list[Candidate] = []

    with DDGS() as ddgs:
        for industry in industries:
            for country in countries:
                for signal in signals:
                    for pattern in signal.get("query_patterns", []):
                        q = pattern.format(industry=industry, country=country)
                        if country:
                            q = f"{q} {country}"
                        try:
                            results = ddgs.text(q, max_results=max_results)
                        except Exception as exc:
                            print(f"[search-error] {q}: {exc}")
                            continue
                        for r in results:
                            url = normalize_url(r.get("href") or r.get("url") or "")
                            if not url:
                                continue
                            host = urlparse(url).netloc.lower()
                            if host in SKIP_HOSTS:
                                continue
                            found.append(Candidate(
                                company=company_from_result(r.get("title", ""), url),
                                website=root_url(url),
                                signal_name=signal["name"],
                                signal_score=int(signal.get("score", 0)),
                                evidence_url=url,
                                evidence_text=(r.get("body") or r.get("snippet") or "")[:1000],
                            ))
                        time.sleep(0.4)
    return found


def fetch_html(client: httpx.Client, url: str) -> str:
    try:
        r = client.get(url, follow_redirects=True)
        if r.status_code >= 400:
            return ""
        ctype = r.headers.get("content-type", "")
        if "text/html" not in ctype:
            return ""
        return r.text[:1_500_000]
    except Exception:
        return ""


def extract_public_emails(html: str, website: str) -> list[str]:
    emails = {e.lower().strip(".,;:()[]{}<>\"'") for e in EMAIL_RE.findall(html or "")}
    host = urlparse(website).netloc.lower().removeprefix("www.")
    good = []
    for e in emails:
        domain = e.split("@")[-1]
        if any(x in e for x in ["example.com", "sentry.io", "wixpress.com", "cloudflare.com"]):
            continue
        if domain == host or domain.endswith("." + host) or domain not in COMMON_FREE_EMAILS:
            good.append(e)
    priority = ["hello@", "info@", "contact@", "sales@", "office@", "admin@", "support@"]
    good.sort(key=lambda e: next((i for i, p in enumerate(priority) if e.startswith(p)), 99))
    return good


def research_candidate(candidate: Candidate, config: dict) -> Candidate:
    crawler = config.get("crawler", {})
    timeout = int(crawler.get("timeout_seconds", 12))
    max_pages = int(crawler.get("max_pages_per_domain", 5))
    ua = crawler.get("user_agent", "Mozilla/5.0")
    pages = ["/", "/contact", "/contact-us", "/about", "/careers", "/jobs"][:max_pages]
    texts: list[str] = []
    emails: list[str] = []

    with httpx.Client(timeout=timeout, headers={"User-Agent": ua}) as client:
        for path in pages:
            url = urljoin(candidate.website, path)
            html = fetch_html(client, url)
            if not html:
                continue
            emails.extend(extract_public_emails(html, candidate.website))
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "noscript", "svg"]):
                tag.decompose()
            text = " ".join(soup.stripped_strings)
            texts.append(text[:12000])

    candidate.email = emails[0] if emails else None
    corpus = " ".join(texts).lower()
    bonus = 0
    signal_terms = {
        "hiring_receptionist": ["receptionist", "front desk", "office coordinator", "customer service representative"],
        "unanswered_calls": ["call us", "phone", "24/7", "after hours"],
        "appointment_friction": ["call to schedule", "call for appointment", "book by phone"],
    }
    for term in signal_terms.get(candidate.signal_name, []):
        if term in corpus:
            bonus += 5
    candidate.score = min(100, candidate.signal_score + bonus)
    return candidate


def save_candidate(conn: sqlite3.Connection, c: Candidate) -> bool:
    fp = fingerprint(c.company, c.website, c.email)
    try:
        conn.execute(
            """INSERT INTO leads
            (fingerprint, company, website, email, signal_name, signal_score, score, evidence_url, evidence_text, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'discovered', ?, ?)""",
            (fp, c.company, c.website, c.email, c.signal_name, c.signal_score, c.score, c.evidence_url, c.evidence_text, now_iso(), now_iso()),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def deterministic_email(row: sqlite3.Row, config: dict) -> tuple[str, str]:
    offer = config["offer"]
    outreach = config["outreach"]
    subject = outreach.get("subject_template", "Quick question about {company}").format(company=row["company"])
    evidence = (row["evidence_text"] or "").strip()
    if evidence:
        opener = f"I came across {row['company']} while looking at businesses showing a possible {row['signal_name'].replace('_', ' ')} signal."
    else:
        opener = f"I came across {row['company']} and noticed a possible {row['signal_name'].replace('_', ' ')} signal."
    body = (
        f"Hi,\n\n{opener}\n\n"
        f"I help businesses with {offer['description']}\n\n"
        f"{offer.get('cta', 'Open to a quick chat?')}\n\n"
        f"Best,\n{offer.get('sender_name', '')}"
    )
    if outreach.get("include_opt_out", True):
        body += "\n\nP.S. If this isn't relevant, reply 'no' and I won't follow up."
    return subject, body


def gmail_service() -> object:
    load_dotenv(ROOT / ".env")
    creds_file = ROOT / os.getenv("GMAIL_CREDENTIALS_FILE", "credentials.json")
    token_file = ROOT / os.getenv("GMAIL_TOKEN_FILE", "token.json")
    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        if not creds_file.exists():
            raise SystemExit(f"Missing Gmail OAuth file: {creds_file}")
        flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
        creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds)


def build_gmail_message(to: str, subject: str, body: str) -> dict:
    msg = MIMEText(body, "plain", "utf-8")
    msg["to"] = to
    msg["subject"] = subject
    msg["date"] = email.utils.formatdate(localtime=True)
    encoded = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {"raw": encoded}


def outreach(conn: sqlite3.Connection, config: dict) -> None:
    conn.row_factory = sqlite3.Row
    min_score = int(config.get("qualification", {}).get("min_score", 35))
    require_email = bool(config.get("qualification", {}).get("require_public_email", True))
    cap = int(config.get("outreach", {}).get("daily_cap", 25))
    mode = config.get("outreach", {}).get("send_mode", "draft").lower()

    rows = conn.execute(
        """SELECT * FROM leads
           WHERE status='discovered' AND score >= ?
           ORDER BY score DESC, created_at ASC LIMIT ?""",
        (min_score, cap),
    ).fetchall()

    if not rows:
        print("No qualified undispatched leads.")
        return

    service = gmail_service()
    count = 0
    for row in rows:
        if require_email and not row["email"]:
            continue
        if not row["email"]:
            continue
        suppressed = conn.execute("SELECT 1 FROM suppressions WHERE email=?", (row["email"],)).fetchone()
        if suppressed:
            continue

        subject, body = deterministic_email(row, config)
        payload = {"message": build_gmail_message(row["email"], subject, body)}
        if mode == "send":
            result = service.users().messages().send(userId="me", body=payload["message"]).execute()
            status = "sent"
        else:
            result = service.users().drafts().create(userId="me", body=payload).execute()
            status = "drafted"

        conn.execute(
            "UPDATE leads SET status=?, subject=?, body=?, gmail_message_id=?, updated_at=? WHERE id=?",
            (status, subject, body, result.get("id", ""), now_iso(), row["id"]),
        )
        conn.commit()
        count += 1
        print(f"[{status}] {row['company']} <{row['email']}> score={row['score']}")
        time.sleep(0.3)
    print(f"Completed: {count} {mode}(s).")


def discover(conn: sqlite3.Connection, config: dict) -> None:
    candidates = search_candidates(config)
    print(f"Search produced {len(candidates)} candidate result(s). Researching...")
    created = 0
    min_score = int(config.get("qualification", {}).get("min_score", 35))
    require_email = bool(config.get("qualification", {}).get("require_public_email", True))

    for i, c in enumerate(candidates, 1):
        c = research_candidate(c, config)
        if c.score < min_score:
            continue
        if require_email and not c.email:
            continue
        if save_candidate(conn, c):
            created += 1
            print(f"[{created}] {c.company} | {c.email or '-'} | score={c.score} | {c.signal_name}")
        if i % 20 == 0:
            time.sleep(0.5)
    print(f"Saved {created} new qualified lead(s).")


def stats(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT status, COUNT(*) FROM leads GROUP BY status ORDER BY status").fetchall()
    total = sum(r[1] for r in rows)
    print(f"Total leads: {total}")
    for status, count in rows:
        print(f"  {status}: {count}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Intent-first agentic outreach engine")
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--outreach", action="store_true")
    parser.add_argument("--gmail-auth", action="store_true")
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    config = load_config()
    conn = init_db()

    if args.gmail_auth:
        gmail_service()
        print("Gmail OAuth ready.")
    elif args.discover:
        discover(conn, config)
    elif args.outreach:
        outreach(conn, config)
    elif args.stats:
        stats(conn)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

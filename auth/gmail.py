import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urlparse

import requests

SUBJECT_PATTERNS = [
    "application received",
    "we received your application",
    "thank you for applying",
    "thanks for applying",
    "application confirmation",
    "your application has been submitted",
    "application submitted",
    "we got your application",
    "your application was sent",
    "application was sent to",
]

BODY_PATTERNS = [
    "we have received your application",
    "thank you for applying to",
    "your application is under review",
    "we have received your resume",
]

EXCLUSION_PATTERNS = [
    "daily digest",
    "weekly digest",
    "update on your application",
    "application update",
    "update on your interview",
    "update from",
    "follow up:",
    "virtual interview",
    "demographic survey",
    "thank you for your interest",
]

ATS_DOMAINS = [
    "greenhouse.io",
    "lever.co",
    "workday.com",
    "icims.com",
    "ashbyhq.com",
    "myworkdayjobs.com",
]

ALL_PHRASE_PATTERNS = SUBJECT_PATTERNS + BODY_PATTERNS

_CONTRACTIONS = {
    "we've": "we have",
    "you've": "you have",
    "we'll": "we will",
    "we're": "we are",
    "it's": "it is",
    "that's": "that is",
    "don't": "do not",
    "didn't": "did not",
    "isn't": "is not",
}

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GMAIL_SCOPE = (
    "https://www.googleapis.com/auth/gmail.readonly "
    "https://www.googleapis.com/auth/calendar.events"
)


def _normalize(text: str) -> str:
    text = text.lower()
    for contraction, expansion in _CONTRACTIONS.items():
        text = text.replace(contraction, expansion)
    return text


_NORMALIZED_PATTERNS = [_normalize(p) for p in ALL_PHRASE_PATTERNS]
_NORMALIZED_EXCLUSIONS = [_normalize(p) for p in EXCLUSION_PATTERNS]


def _is_excluded(text: str) -> bool:
    normalized = _normalize(text)
    return any(p in normalized for p in _NORMALIZED_EXCLUSIONS)


def _gmail_redirect_uri() -> str:
    base = os.getenv("REDIRECT_URL", "http://localhost:8000/auth/callback")
    parsed = urlparse(base)
    return f"{parsed.scheme}://{parsed.netloc}/auth/gmail/callback"


def get_gmail_auth_url() -> str:
    params = {
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "redirect_uri": _gmail_redirect_uri(),
        "response_type": "code",
        "scope": _GMAIL_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"


def exchange_code_for_tokens(code: str) -> dict:
    resp = requests.post(
        _GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "redirect_uri": _gmail_redirect_uri(),
            "grant_type": "authorization_code",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def refresh_access_token(refresh_token: str) -> str:
    resp = requests.post(
        _GOOGLE_TOKEN_URL,
        data={
            "refresh_token": refresh_token,
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


_COMPANY_PATTERNS = [
    r"your application was sent to (.+)",
    r"application was sent to (.+)",
    r"thank you for applying to (.+)",
    r"thanks for applying to (.+)",
    r"your application to (.+?) has been",
    r"thank you for your interest in (.+)",
    r"you(?:'ve| have) applied (?:to|for) (.+)",
]


def _extract_company(subject: str) -> str | None:
    normalized = _normalize(subject)
    for pattern in _COMPANY_PATTERNS:
        m = re.search(pattern, normalized)
        if m:
            raw = m.group(1).strip()
            raw = re.sub(r"[!.,;:]+$", "", raw).strip()
            raw = re.sub(r"\s+(?:position|role|job|opening|opportunity)\b.*$", "", raw).strip()
            return raw if raw else None
    return None


def _normalize_company(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"\s*\b(?:inc|llc|ltd|corp|co|company|group|technologies|solutions|services)\b\.?\s*$", "", name).strip()
    return name


def get_email_address(access_token: str) -> str:
    resp = requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    if not resp.ok:
        return ""
    return resp.json().get("email", "")


def _extract_domain(from_header: str) -> str:
    match = re.search(r"@([\w.-]+)", from_header)
    return match.group(1).lower() if match else ""


def _matches(text: str) -> bool:
    normalized = _normalize(text)
    return any(p in normalized for p in _NORMALIZED_PATTERNS)


_GMAIL_SUBJECT_QUERY = " OR ".join(
    f'subject:"{p}"' for p in SUBJECT_PATTERNS
)
_ATS_SENDER_QUERY = " OR ".join(f"from:{d}" for d in ATS_DOMAINS)


def scan_recent_applications(access_token: str, days_back: int = 1) -> list[dict]:
    headers = {"Authorization": f"Bearer {access_token}"}

    search_query = f"newer_than:{days_back}d ({_GMAIL_SUBJECT_QUERY} OR {_ATS_SENDER_QUERY})"
    list_resp = requests.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages",
        headers=headers,
        params={"q": search_query, "maxResults": 50},
        timeout=15,
    )
    list_resp.raise_for_status()
    message_ids = [m["id"] for m in list_resp.json().get("messages", [])]

    results = []
    for msg_id in message_ids:
        detail_resp = requests.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}",
            headers=headers,
            params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
            timeout=15,
        )
        if not detail_resp.ok:
            continue
        detail = detail_resp.json()
        header_map = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
        subject = header_map.get("Subject", "")
        from_header = header_map.get("From", "")
        snippet = detail.get("snippet", "")
        sender_domain = _extract_domain(from_header)

        if _is_excluded(subject) or _is_excluded(snippet):
            continue

        matched_via = None
        if _matches(subject):
            matched_via = "subject"
        elif _matches(snippet):
            matched_via = "body"
        elif any(domain in sender_domain for domain in ATS_DOMAINS):
            matched_via = "sender_domain"

        if matched_via:
            try:
                email_date = parsedate_to_datetime(header_map.get("Date", "")).isoformat()
            except (TypeError, ValueError):
                email_date = datetime.now(timezone.utc).isoformat()
            results.append(
                {
                    "gmail_message_id": msg_id,
                    "subject": subject,
                    "sender_domain": sender_domain,
                    "matched_via": matched_via,
                    "email_date": email_date,
                }
            )
    return results


_CALENDAR_COMPANY_PATTERNS = [
    r"(?:phone\s+)?screen(?:ing)?\s*[-–|]\s*(.+)",
    r"(.+?)\s*[-–|]\s*(?:phone\s+)?screen(?:ing)?",
    r"interview\s+with\s+.+?\s+(?:at|@)\s+(.+)",
    r"(.+?)\s+interview",
    r"interview\s*[-–|]\s*(.+)",
    r"recruiter\s+call\s*[-–|]\s*(.+)",
    r"(.+?)\s+recruiter\s+call",
    r"hiring\s+call\s*[-–|]\s*(.+)",
    r"(.+?)\s*[-–|@]\s*(.+)",
]

_SKIP_DOMAINS = {"gmail.com", "google.com", "googlemail.com", "outlook.com", "hotmail.com", "yahoo.com"}


def _extract_company_from_event(title: str, organizer_email: str) -> str | None:
    normalized = title.lower().strip()
    for pattern in _CALENDAR_COMPANY_PATTERNS[:-1]:
        m = re.search(pattern, normalized)
        if m:
            raw = m.group(1).strip(" -–|@")
            raw = re.sub(r"\s+", " ", raw).strip()
            if raw and len(raw) > 1:
                return raw.title()
    domain = _extract_domain(organizer_email)
    if domain and domain not in _SKIP_DOMAINS:
        return domain.split(".")[0].title()
    return None


def create_calendar_event(access_token: str, title: str, date: str, description: str = "") -> dict:
    """Create an all-day event on the user's primary Google Calendar."""
    resp = requests.post(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={
            "summary": title,
            "description": description,
            "start": {"date": date},
            "end": {"date": date},
            "reminders": {
                "useDefault": False,
                "overrides": [{"method": "popup", "minutes": 540}],
            },
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_upcoming_events(access_token: str, days_ahead: int = 14) -> list[dict]:
    from datetime import timedelta
    headers = {"Authorization": f"Bearer {access_token}"}
    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=days_ahead)).isoformat()

    resp = requests.get(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        headers=headers,
        params={
            "timeMin": time_min,
            "timeMax": time_max,
            "singleEvents": True,
            "orderBy": "startTime",
            "maxResults": 50,
        },
        timeout=15,
    )
    if not resp.ok:
        raise RuntimeError(f"Calendar API error {resp.status_code}: {resp.text[:300]}")
    items = resp.json().get("items", [])

    events = []
    for item in items:
        start = item.get("start", {})
        event_dt = start.get("dateTime") or start.get("date", "")
        organizer = item.get("organizer", {})
        organizer_email = organizer.get("email", "")
        attendees = [
            {"email": a.get("email", ""), "name": a.get("displayName", "")}
            for a in item.get("attendees", [])
            if not a.get("self")
        ]
        title = item.get("summary", "Untitled event")
        company = _extract_company_from_event(title, organizer_email)
        events.append({
            "id": item.get("id", ""),
            "title": title,
            "start": event_dt,
            "organizer_email": organizer_email,
            "organizer_name": organizer.get("displayName", ""),
            "attendees": attendees,
            "meet_link": item.get("hangoutLink", ""),
            "company": company,
        })
    return events

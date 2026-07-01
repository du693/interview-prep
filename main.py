import asyncio
import io
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

import psycopg2

from pydantic import BaseModel

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pypdf import PdfReader

import pdf_report
from agents import researcher, scraper, synthesizer
from agents.synthesizer import STAGE_LABELS
from auth.google import get_google_auth_url, supabase, supabase_admin
from auth.gmail import (
    _extract_company,
    _normalize_company,
    create_calendar_event,
    exchange_code_for_tokens,
    fetch_upcoming_events,
    get_email_address,
    get_gmail_auth_url,
    refresh_access_token,
    scan_recent_applications,
)
from sample_briefing import SAMPLE_COMPANY_NAME, SAMPLE_JOB_TITLE, SAMPLE_RESULT, SAMPLE_STAGES

def _psycopg2_url(raw: str) -> str:
    """Strip SQLAlchemy driver prefix and pooler query params so psycopg2 can parse the URL."""
    url = raw.split("?")[0]  # drop ?pgbouncer and any other query params
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg2://", "postgres+asyncpg://"):
        if url.startswith(prefix):
            url = "postgresql://" + url[len(prefix):]
            break
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def _migrate_db():
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        logging.warning("DB migration skipped: DATABASE_URL not set")
        return
    try:
        conn = psycopg2.connect(_psycopg2_url(db_url))
        cur = conn.cursor()
        cur.execute("ALTER TABLE pipeline_entries ADD COLUMN IF NOT EXISTS notes TEXT DEFAULT ''")
        cur.execute("ALTER TABLE pipeline_entries ADD COLUMN IF NOT EXISTS comp_range TEXT DEFAULT ''")
        cur.execute("ALTER TABLE pipeline_entries ADD COLUMN IF NOT EXISTS company_url TEXT DEFAULT ''")
        cur.execute("ALTER TABLE pipeline_entries ADD COLUMN IF NOT EXISTS role_level TEXT DEFAULT ''")
        cur.execute("ALTER TABLE scheduled_interviews ADD COLUMN IF NOT EXISTS person TEXT DEFAULT ''")
        conn.commit()
        cur.close()
        conn.close()
        logging.info("DB migration complete")
    except Exception as e:
        logging.error(f"DB migration error: {e}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _migrate_db()
    # Tell PostgREST to reload its schema cache so new columns are visible
    try:
        supabase_admin.rpc("pg_notify", {"channel": "pgrst", "payload": "reload schema"}).execute()
    except Exception:
        pass  # pg_notify may not be RPC-accessible; schema refresh is best-effort
    scheduler.add_job(_scheduled_gmail_scan_all, "interval", minutes=15, id="gmail_scan")
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
scheduler = AsyncIOScheduler()
templates = Jinja2Templates(directory="templates")
templates.env.globals["cache_bust"] = str(int(time.time()))
logger = logging.getLogger("uvicorn.error")

jobs: dict[str, dict] = {}

MAX_FINDINGS_CHARS = 1500
MAX_INPUT_CHARS = 3000
SUBMIT_COOLDOWN_SECONDS = 90

last_submitted_at: float = 0.0


def _extract_resume_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = (" ".join((page.extract_text() or "").split()) for page in reader.pages)
    return "\n".join(pages)


STAGE_CONTEXT_FIELDS = {
    "behavioral": [("behavioral_focus", "What they seem to value most")],
    "technical": [
        ("tech_assessment_type", "Assessment type"),
        ("tech_topics", "Topics likely tested"),
    ],
    "roleplay": [
        ("roleplay_scenario", "Scenario"),
        ("roleplay_specifics", "Specifics to handle"),
    ],
    "panel": [
        ("panel_makeup", "Panel makeup"),
        ("panel_structure", "Panel structure"),
    ],
    "final": [("final_trajectory", "Company trajectory")],
}


def _build_stage_context(stage_type: str, fields: dict[str, str]) -> str:
    lines = []
    for name, label in STAGE_CONTEXT_FIELDS.get(stage_type, []):
        value = fields.get(name, "").strip()
        if value:
            lines.append(f"{label}: {value}")
    return "\n".join(lines)


async def get_current_user(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Please sign in to generate a briefing.")
    token = authorization.replace("Bearer ", "")
    try:
        user = supabase.auth.get_user(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Your session has expired — please sign in again.")
    if user is None:
        raise HTTPException(status_code=401, detail="Your session has expired — please sign in again.")
    return user.user


async def get_current_user_for_download(authorization: str = Header(None), token: str = ""):
    raw_token = (authorization.replace("Bearer ", "") if authorization else "") or token
    if not raw_token:
        raise HTTPException(status_code=401, detail="Please sign in to download this briefing.")
    try:
        user = supabase.auth.get_user(raw_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Your session has expired — please sign in again.")
    if user is None:
        raise HTTPException(status_code=401, detail="Your session has expired — please sign in again.")
    return user.user


async def get_current_user_optional(authorization: str = Header(None)):
    if not authorization:
        return None
    token = authorization.replace("Bearer ", "")
    try:
        user = supabase.auth.get_user(token)
    except Exception:
        return None
    return user.user if user else None


def _build_briefing_title(company_name: str, job_title: str, stage_type: str) -> str:
    stage_label = STAGE_LABELS.get(stage_type, "Intro call")
    return f"{company_name} — {stage_label} — {job_title}"


def _save_briefing(user_id: str, company_name: str, job_title: str, stage_type: str, result: dict, is_sample: bool):
    try:
        if is_sample:
            existing = (
                supabase_admin.table("briefings")
                .select("id")
                .eq("user_id", user_id)
                .eq("is_sample", True)
                .limit(1)
                .execute()
            )
            if existing.data:
                return
        supabase_admin.table("briefings").insert(
            {
                "user_id": user_id,
                "title": _build_briefing_title(company_name, job_title, stage_type),
                "company_name": company_name,
                "job_title": job_title,
                "stage_type": stage_type,
                "is_sample": is_sample,
                "result": result,
            }
        ).execute()
    except Exception:
        logger.exception("Failed to save briefing for user %s", user_id)


async def _run_briefing_job(
    job_id: str,
    job_title: str,
    role_level: str,
    company_name: str,
    company_url: str,
    job_description: str,
    resume_text: str,
    interviewer_name: str,
    interviewer_title: str,
    stage_type: str,
    stage_context: str,
    user_id: str,
):
    try:
        jobs[job_id]["stage"] = f"Researching {company_name} and scanning their site..."
        research_task = researcher.research(company_name, job_title, interviewer_name, interviewer_title)
        scrape_task = asyncio.to_thread(scraper.scrape, company_url)
        research_findings, scrape_findings = await asyncio.gather(research_task, scrape_task)
        research_findings = research_findings[:MAX_FINDINGS_CHARS]
        scrape_findings = scrape_findings[:MAX_FINDINGS_CHARS]

        jobs[job_id]["stage"] = "Writing your briefing..."
        result = await synthesizer.synthesize(
            job_title,
            role_level,
            company_name,
            job_description[:MAX_INPUT_CHARS],
            resume_text[:MAX_INPUT_CHARS],
            interviewer_name,
            interviewer_title,
            research_findings,
            scrape_findings,
            stage_type,
            stage_context,
        )
        jobs[job_id] = {
            "status": "done",
            "result": result,
            "company_name": company_name,
            "job_title": job_title,
            "stage_type": stage_type,
        }
        _save_briefing(user_id, company_name, job_title, stage_type, result, is_sample=False)
    except Exception as exc:
        logger.exception("Briefing job %s failed", job_id)
        jobs[job_id] = {"status": "error", "error": str(exc)}


async def _run_sample_job(job_id: str, user_id: str | None):
    for stage in SAMPLE_STAGES:
        jobs[job_id]["stage"] = stage
        await asyncio.sleep(1)
    if user_id:
        _save_briefing(user_id, SAMPLE_COMPANY_NAME, SAMPLE_JOB_TITLE, "intro_call", SAMPLE_RESULT, is_sample=True)
    jobs[job_id] = {
        "status": "done",
        "result": SAMPLE_RESULT,
        "company_name": SAMPLE_COMPANY_NAME,
        "job_title": SAMPLE_JOB_TITLE,
        "stage_type": "intro_call",
    }


async def _scheduled_gmail_scan_all():
    try:
        connections = (
            supabase_admin.table("gmail_connections")
            .select("user_id, refresh_token")
            .not_.is_("refresh_token", "null")
            .execute()
        )
    except Exception:
        logger.exception("Scheduled Gmail scan: failed to fetch connections")
        return
    for conn in connections.data:
        try:
            access_token = await asyncio.to_thread(refresh_access_token, conn["refresh_token"])
            await asyncio.to_thread(_run_gmail_scan, conn["user_id"], access_token)
        except Exception:
            logger.exception("Scheduled Gmail scan failed for user %s", conn["user_id"])



@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse(request, "landing.html")


@app.get("/app", response_class=HTMLResponse)
async def index(request: Request):
    session = _get_dashboard_session(request)
    resp = templates.TemplateResponse(
        request,
        "index.html",
        {
            "access_token": session["access_token"] if session else "",
            "user_email": session["user_email"] if session else "",
        },
    )
    if session:
        _apply_session_cookie(resp, session)
    return resp


@app.get("/auth/status")
async def auth_status(request: Request):
    session = _get_dashboard_session(request)
    return JSONResponse({"logged_in": session is not None})


@app.get("/auth/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return response


@app.get("/auth/google")
async def google_login():
    url = get_google_auth_url()
    return RedirectResponse(url)


@app.get("/auth/callback")
async def google_callback(code: str):
    session = supabase.auth.exchange_code_for_session({"auth_code": code})
    access_token = session.session.access_token
    refresh_token = session.session.refresh_token or ""
    response = RedirectResponse(url="/dashboard")
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=True, samesite="lax")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=True, samesite="lax")
    return response


def _get_dashboard_session(request: Request):
    token = request.cookies.get("access_token")
    refresh_token = request.cookies.get("refresh_token")
    new_access_token = None

    user_response = None
    if token:
        try:
            user_response = supabase.auth.get_user(token)
            if user_response and user_response.user is None:
                user_response = None
        except Exception:
            user_response = None

    # Access token missing or expired — try refresh
    if user_response is None and refresh_token:
        try:
            refreshed = supabase.auth.refresh_session(refresh_token)
            if refreshed and refreshed.session:
                new_access_token = refreshed.session.access_token
                token = new_access_token
                user_response = supabase.auth.get_user(token)
        except Exception:
            return None

    if user_response is None or user_response.user is None:
        return None

    user = user_response.user
    metadata = user.user_metadata or {}
    full_name = metadata.get("full_name") or metadata.get("name") or user.email or "there"
    initials = "".join(part[0] for part in full_name.split()[:2]).upper() or "?"
    return {
        "user": user,
        "user_name": full_name,
        "user_email": user.email or "",
        "user_initials": initials,
        "access_token": token,
        "_new_access_token": new_access_token,
    }


def _apply_session_cookie(response, session: dict):
    """Set a refreshed access_token cookie if the session was silently renewed."""
    new_token = session.get("_new_access_token") if session else None
    if new_token:
        response.set_cookie(key="access_token", value=new_token, httponly=True, secure=True, samesite="lax")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    session = _get_dashboard_session(request)
    if session is None:
        return RedirectResponse(url="/")

    resp = templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user_name": session["user_name"],
            "user_email": session["user_email"],
            "user_initials": session["user_initials"],
            "access_token": session["access_token"],
        },
    )
    _apply_session_cookie(resp, session)
    return resp


@app.get("/pipeline", response_class=HTMLResponse)
async def pipeline_page(request: Request):
    session = _get_dashboard_session(request)
    if session is None:
        return RedirectResponse(url="/")
    resp = templates.TemplateResponse(
        request,
        "pipeline.html",
        {
            "user_name": session["user_name"],
            "user_email": session["user_email"],
            "user_initials": session["user_initials"],
            "access_token": session["access_token"],
        },
    )
    _apply_session_cookie(resp, session)
    return resp


@app.get("/saved-briefings", response_class=HTMLResponse)
async def saved_briefings_page(request: Request):
    session = _get_dashboard_session(request)
    if session is None:
        return RedirectResponse(url="/")

    resp = templates.TemplateResponse(
        request,
        "saved-briefings.html",
        {
            "user_name": session["user_name"],
            "user_email": session["user_email"],
            "user_initials": session["user_initials"],
            "access_token": session["access_token"],
        },
    )
    _apply_session_cookie(resp, session)
    return resp


LINKEDIN_SUPPRESSION_WINDOW_SECONDS = 4 * 3600


def _parse_email_dt(dt_str: str) -> datetime | None:
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return None


def _run_gmail_scan(user_id: str, access_token: str, days_back: int = 1):
    logger.info("Gmail scan starting for user %s (days_back=%d)", user_id, days_back)
    matches = scan_recent_applications(access_token, days_back=days_back)
    logger.info("Gmail scan: %d raw matches found for user %s", len(matches), user_id)
    for m in matches:
        logger.info("  RAW MATCH | %s | %s | via=%s", m["sender_domain"], m["subject"], m["matched_via"])

    if not matches:
        supabase_admin.table("gmail_connections").update(
            {"last_scanned_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        ).eq("user_id", user_id).execute()
        return

    existing_resp = (
        supabase_admin.table("gmail_applications")
        .select("gmail_message_id, subject, sender_domain, email_date")
        .eq("user_id", user_id)
        .execute()
    )
    existing = existing_resp.data or []
    existing_ids = {rec["gmail_message_id"] for rec in existing}

    # (normalized company, date) pairs already stored, used to dedupe by company+day
    seen_companies: set[tuple[str, str]] = set()
    for rec in existing:
        company = _extract_company(rec.get("subject", ""))
        if company:
            seen_companies.add((_normalize_company(company), rec["email_date"][:10]))

    all_context = existing + matches  # for the LinkedIn time-window fallback check

    to_upsert = []
    for match in matches:
        if match["gmail_message_id"] in existing_ids:
            logger.info("  SKIP (already stored) | %s", match["subject"])
            continue

        company = _extract_company(match["subject"])
        date_str = match["email_date"][:10]

        if company:
            key = (_normalize_company(company), date_str)
            if key in seen_companies:
                logger.info("  SKIP (company dedup: %s on %s) | %s", _normalize_company(company), date_str, match["subject"])
                continue
            seen_companies.add(key)
        elif match["sender_domain"] == "linkedin.com":
            match_dt = _parse_email_dt(match["email_date"])
            if match_dt:
                suppress = False
                for rec in all_context:
                    if rec.get("sender_domain") == "linkedin.com":
                        continue
                    if rec.get("gmail_message_id") == match["gmail_message_id"]:
                        continue
                    rec_dt = _parse_email_dt(rec.get("email_date", ""))
                    if rec_dt and abs((match_dt - rec_dt).total_seconds()) <= LINKEDIN_SUPPRESSION_WINDOW_SECONDS:
                        suppress = True
                        break
                if suppress:
                    logger.info("  SKIP (linkedin suppressed within 4h) | %s", match["subject"])
                    continue

        logger.info("  INSERT | %s | %s", match["sender_domain"], match["subject"])
        to_upsert.append(match)
        existing_ids.add(match["gmail_message_id"])

    for match in to_upsert:
        try:
            supabase_admin.table("gmail_applications").upsert(
                {
                    "user_id": user_id,
                    "gmail_message_id": match["gmail_message_id"],
                    "subject": match["subject"],
                    "sender_domain": match["sender_domain"],
                    "matched_via": match["matched_via"],
                    "email_date": match["email_date"],
                },
                on_conflict="user_id,gmail_message_id",
            ).execute()
        except Exception:
            logger.exception("Failed to upsert gmail application for user %s", user_id)

    logger.info("Gmail scan complete: %d new record(s) inserted for user %s", len(to_upsert), user_id)
    supabase_admin.table("gmail_connections").update(
        {"last_scanned_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    ).eq("user_id", user_id).execute()


@app.get("/auth/gmail")
async def gmail_login():
    return RedirectResponse(get_gmail_auth_url())


@app.get("/auth/gmail/callback")
async def gmail_callback(code: str, request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/dashboard?gmail=error")
    try:
        user = supabase.auth.get_user(token).user
    except Exception:
        return RedirectResponse(url="/dashboard?gmail=error")

    try:
        tokens = exchange_code_for_tokens(code)
    except Exception:
        logger.exception("Gmail token exchange failed")
        return RedirectResponse(url="/dashboard?gmail=error")

    access_token = tokens.get("access_token")
    if not access_token:
        return RedirectResponse(url="/dashboard?gmail=error")

    email_address = get_email_address(access_token)
    supabase_admin.table("gmail_connections").upsert(
        {
            "user_id": user.id,
            "email_address": email_address,
            "refresh_token": tokens.get("refresh_token"),
        },
        on_conflict="user_id",
    ).execute()

    _run_gmail_scan(user.id, access_token, days_back=30)

    return RedirectResponse(url="/dashboard?gmail=connected")


@app.post("/gmail/rescan")
async def gmail_rescan(user=Depends(get_current_user)):
    conn = (
        supabase_admin.table("gmail_connections")
        .select("refresh_token, last_scanned_at")
        .eq("user_id", user.id)
        .limit(1)
        .execute()
    )
    if not conn.data or not conn.data[0].get("refresh_token"):
        logger.warning("Gmail rescan: no refresh token stored for user %s", user.id)
        return JSONResponse({"error": "no_refresh_token"}, status_code=400)
    try:
        access_token = refresh_access_token(conn.data[0]["refresh_token"])
    except Exception as exc:
        logger.exception("Gmail rescan: token refresh failed for user %s", user.id)
        return JSONResponse({"error": str(exc)}, status_code=401)

    last_scanned_at = conn.data[0].get("last_scanned_at")
    if last_scanned_at:
        last_dt = _parse_email_dt(last_scanned_at)
        if last_dt:
            days_since = (datetime.now(timezone.utc) - last_dt).days
            days_back = max(1, days_since + 1)
        else:
            days_back = 30
    else:
        days_back = 30
    days_back = min(days_back, 30)

    async def _scan_task():
        try:
            await asyncio.to_thread(_run_gmail_scan, user.id, access_token, days_back)
        except Exception:
            logger.exception("Gmail background scan failed for user %s", user.id)

    asyncio.create_task(_scan_task())
    return JSONResponse({"status": "scanning"})


@app.get("/gmail/debug-scan")
async def gmail_debug_scan(request: Request):
    session = _get_dashboard_session(request)
    if session is None:
        return JSONResponse({"error": "not_logged_in"}, status_code=401)
    user = session["user"]
    conn = (
        supabase_admin.table("gmail_connections")
        .select("refresh_token")
        .eq("user_id", user.id)
        .limit(1)
        .execute()
    )
    if not conn.data or not conn.data[0].get("refresh_token"):
        return JSONResponse({"error": "not_connected"}, status_code=400)
    try:
        access_token = refresh_access_token(conn.data[0]["refresh_token"])
    except Exception as exc:
        return JSONResponse({"error": f"token_refresh_failed: {exc}"}, status_code=401)

    import requests as _req
    from auth.gmail import _GMAIL_SUBJECT_QUERY, _ATS_SENDER_QUERY
    headers = {"Authorization": f"Bearer {access_token}"}
    search_query = f"newer_than:7d ({_GMAIL_SUBJECT_QUERY} OR {_ATS_SENDER_QUERY})"
    list_resp = _req.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages",
        headers=headers,
        params={"q": search_query, "maxResults": 20},
        timeout=15,
    )
    if not list_resp.ok:
        return JSONResponse({"error": f"gmail_api_{list_resp.status_code}", "detail": list_resp.text})

    message_ids = [m["id"] for m in list_resp.json().get("messages", [])]
    raw = []
    for msg_id in message_ids[:10]:
        detail = _req.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}",
            headers=headers,
            params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
            timeout=15,
        ).json()
        header_map = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
        raw.append({
            "subject": header_map.get("Subject", ""),
            "from": header_map.get("From", ""),
            "date": header_map.get("Date", ""),
            "snippet": detail.get("snippet", "")[:120],
        })

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stored_today = (
        supabase_admin.table("gmail_applications")
        .select("subject, sender_domain, email_date, matched_via")
        .eq("user_id", user.id)
        .gte("email_date", f"{today}T00:00:00+00:00")
        .execute()
    )
    all_stored = (
        supabase_admin.table("gmail_applications")
        .select("subject, sender_domain, email_date, matched_via")
        .eq("user_id", user.id)
        .order("email_date", desc=True)
        .limit(5)
        .execute()
    )
    conn_info = (
        supabase_admin.table("gmail_connections")
        .select("last_scanned_at")
        .eq("user_id", user.id)
        .limit(1)
        .execute()
    )
    return JSONResponse({
        "today_utc": today,
        "last_scanned_at": conn_info.data[0]["last_scanned_at"] if conn_info.data else None,
        "gmail_found": len(message_ids),
        "sample_emails": raw,
        "stored_today_count": len(stored_today.data or []),
        "stored_today": stored_today.data or [],
        "most_recent_5_stored": all_stored.data or [],
    })


@app.get("/gmail/status")
async def gmail_status(user=Depends(get_current_user), day_start: str = None):
    conn = (
        supabase_admin.table("gmail_connections")
        .select("email_address, connected_at, last_scanned_at")
        .eq("user_id", user.id)
        .limit(1)
        .execute()
    )
    if not conn.data:
        return JSONResponse({"connected": False})

    # day_start is "start of today in the user's local timezone" sent as UTC ISO string
    # Falls back to UTC midnight if not provided
    if not day_start:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        day_start = f"{today}T00:00:00+00:00"

    count_resp = (
        supabase_admin.table("gmail_applications")
        .select("id", count="exact")
        .eq("user_id", user.id)
        .execute()
    )
    today_resp = (
        supabase_admin.table("gmail_applications")
        .select("id", count="exact")
        .eq("user_id", user.id)
        .gte("email_date", day_start)
        .execute()
    )
    return JSONResponse(
        {
            "connected": True,
            "email_address": conn.data[0]["email_address"],
            "last_scanned_at": conn.data[0]["last_scanned_at"],
            "application_count": count_resp.count or 0,
            "applications_today": today_resp.count or 0,
        }
    )


# ── Interviews ───────────────────────────────────────────────────────────────

class InterviewCreate(BaseModel):
    company: str = ""
    role: str = ""
    person: str = ""
    date: str = ""
    stage: str = ""
    prepped: bool = False
    calEventId: str = ""
    reviewed: bool = False
    review: Optional[dict] = None

class InterviewUpdate(BaseModel):
    company: Optional[str] = None
    role: Optional[str] = None
    person: Optional[str] = None
    date: Optional[str] = None
    stage: Optional[str] = None
    prepped: Optional[bool] = None
    calEventId: Optional[str] = None
    reviewed: Optional[bool] = None
    review: Optional[dict] = None


def _interview_to_js(row: dict) -> dict:
    return {
        "id": row["id"],
        "company": row.get("company", ""),
        "role": row.get("role", ""),
        "person": row.get("person", ""),
        "date": row.get("date", ""),
        "stage": row.get("stage", ""),
        "prepped": row.get("prepped", False),
        "calEventId": row.get("cal_event_id", ""),
        "reviewed": row.get("reviewed", False),
        "review": row.get("review"),
    }


def _interview_from_js(data: dict) -> dict:
    out = {}
    for k in ("company", "role", "person", "date", "stage", "prepped", "reviewed", "review"):
        if k in data:
            out[k] = data[k]
    if "calEventId" in data:
        out["cal_event_id"] = data["calEventId"]
    return out


@app.get("/interviews")
async def get_interviews(user=Depends(get_current_user)):
    resp = (
        supabase_admin.table("scheduled_interviews")
        .select("*").eq("user_id", user.id).order("date").execute()
    )
    return JSONResponse({"interviews": [_interview_to_js(r) for r in (resp.data or [])]})


@app.post("/interviews")
async def create_interview(body: InterviewCreate, user=Depends(get_current_user)):
    row = _interview_from_js(body.model_dump())
    row["user_id"] = user.id
    try:
        resp = supabase_admin.table("scheduled_interviews").insert(row).execute()
    except Exception as e:
        if "person" in str(e):
            row.pop("person", None)
            resp = supabase_admin.table("scheduled_interviews").insert(row).execute()
        else:
            raise
    return JSONResponse(_interview_to_js(resp.data[0]))


@app.patch("/interviews/{interview_id}")
async def update_interview(interview_id: str, body: InterviewUpdate, user=Depends(get_current_user)):
    updates = _interview_from_js({k: v for k, v in body.model_dump(exclude_unset=True).items()})
    if not updates:
        return JSONResponse({"ok": True})
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    resp = (
        supabase_admin.table("scheduled_interviews")
        .update(updates).eq("id", interview_id).eq("user_id", user.id).execute()
    )
    return JSONResponse(_interview_to_js(resp.data[0]) if resp.data else {"ok": True})


@app.delete("/interviews/{interview_id}")
async def delete_interview(interview_id: str, user=Depends(get_current_user)):
    supabase_admin.table("scheduled_interviews").delete().eq("id", interview_id).eq("user_id", user.id).execute()
    return JSONResponse({"ok": True})


# ── Follow-up reminders ───────────────────────────────────────────────────────

class FollowupCreate(BaseModel):
    type: str = "followup"
    company: str = ""
    role: str = ""
    person: str = ""
    date: str = ""
    notes: str = ""
    completed: bool = False

class FollowupUpdate(BaseModel):
    type: Optional[str] = None
    company: Optional[str] = None
    role: Optional[str] = None
    person: Optional[str] = None
    date: Optional[str] = None
    notes: Optional[str] = None
    completed: Optional[bool] = None


@app.get("/followups")
async def get_followups(user=Depends(get_current_user)):
    resp = (
        supabase_admin.table("followup_reminders")
        .select("*").eq("user_id", user.id).order("date").execute()
    )
    return JSONResponse({"followups": resp.data or []})


@app.post("/followups")
async def create_followup(body: FollowupCreate, user=Depends(get_current_user)):
    row = body.model_dump()
    row["user_id"] = user.id
    resp = supabase_admin.table("followup_reminders").insert(row).execute()
    return JSONResponse(resp.data[0])


@app.patch("/followups/{followup_id}")
async def update_followup(followup_id: str, body: FollowupUpdate, user=Depends(get_current_user)):
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    if not updates:
        return JSONResponse({"ok": True})
    resp = (
        supabase_admin.table("followup_reminders")
        .update(updates).eq("id", followup_id).eq("user_id", user.id).execute()
    )
    return JSONResponse(resp.data[0] if resp.data else {"ok": True})


@app.delete("/followups/{followup_id}")
async def delete_followup_entry(followup_id: str, user=Depends(get_current_user)):
    supabase_admin.table("followup_reminders").delete().eq("id", followup_id).eq("user_id", user.id).execute()
    return JSONResponse({"ok": True})


# ── Pipeline ─────────────────────────────────────────────────────────────────

class PipelineEntryCreate(BaseModel):
    company: str
    role: str = ""
    status: str = "prep"
    screeningDate: str = ""
    calEventId: str = ""
    rounds: List[Any] = []
    addedAt: str = ""
    notes: str = ""
    compRange: str = ""
    companyUrl: str = ""
    roleLevel: str = ""

class PipelineEntryUpdate(BaseModel):
    company: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    screeningDate: Optional[str] = None
    calEventId: Optional[str] = None
    rounds: Optional[List[Any]] = None
    addedAt: Optional[str] = None
    notes: Optional[str] = None
    compRange: Optional[str] = None
    companyUrl: Optional[str] = None
    roleLevel: Optional[str] = None


def _entry_to_js(row: dict) -> dict:
    return {
        "id": row["id"],
        "company": row.get("company", ""),
        "role": row.get("role", ""),
        "status": row.get("status", "prep"),
        "screeningDate": row.get("screening_date", ""),
        "calEventId": row.get("cal_event_id", ""),
        "rounds": row.get("rounds") or [],
        "addedAt": row.get("added_at", ""),
        "notes": row.get("notes", ""),
        "compRange": row.get("comp_range", ""),
        "companyUrl": row.get("company_url", ""),
        "roleLevel": row.get("role_level", ""),
    }


def _entry_from_js(data: dict) -> dict:
    out = {}
    mapping = {
        "company": "company", "role": "role", "status": "status",
        "screeningDate": "screening_date", "calEventId": "cal_event_id",
        "rounds": "rounds", "addedAt": "added_at",
        "notes": "notes", "compRange": "comp_range",
        "companyUrl": "company_url", "roleLevel": "role_level",
    }
    for js_key, db_key in mapping.items():
        if js_key in data and data[js_key] is not None:
            out[db_key] = data[js_key]
    return out


@app.get("/pipeline/entries")
async def get_pipeline_entries(user=Depends(get_current_user)):
    resp = (
        supabase_admin.table("pipeline_entries")
        .select("*")
        .eq("user_id", user.id)
        .order("created_at")
        .execute()
    )
    return JSONResponse({"entries": [_entry_to_js(r) for r in (resp.data or [])]})


@app.get("/pipeline/entries/{entry_id}")
async def get_pipeline_entry(entry_id: str, user=Depends(get_current_user)):
    resp = (
        supabase_admin.table("pipeline_entries")
        .select("*")
        .eq("id", entry_id)
        .eq("user_id", user.id)
        .limit(1)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Entry not found")
    return JSONResponse(_entry_to_js(resp.data[0]))


@app.post("/pipeline/entries")
async def create_pipeline_entry(body: PipelineEntryCreate, user=Depends(get_current_user)):
    row = _entry_from_js(body.model_dump())
    row["user_id"] = user.id
    resp = supabase_admin.table("pipeline_entries").insert(row).execute()
    return JSONResponse(_entry_to_js(resp.data[0]))


@app.patch("/pipeline/entries/{entry_id}")
async def update_pipeline_entry(entry_id: str, body: PipelineEntryUpdate, user=Depends(get_current_user)):
    updates = _entry_from_js({k: v for k, v in body.model_dump().items() if v is not None})
    if not updates:
        return JSONResponse({"ok": True})
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    resp = (
        supabase_admin.table("pipeline_entries")
        .update(updates)
        .eq("id", entry_id)
        .eq("user_id", user.id)
        .execute()
    )
    return JSONResponse(_entry_to_js(resp.data[0]) if resp.data else {"ok": True})


@app.delete("/pipeline/entries/{entry_id}")
async def delete_pipeline_entry(entry_id: str, user=Depends(get_current_user)):
    supabase_admin.table("pipeline_entries").delete().eq("id", entry_id).eq("user_id", user.id).execute()
    return JSONResponse({"ok": True})


class RecruiterScreenCreate(BaseModel):
    company_name: str
    job_title: str = ""
    notes: str = ""
    comp_range: str = ""


@app.post("/recruiter-screen")
async def save_recruiter_screen(body: RecruiterScreenCreate, user=Depends(get_current_user)):
    row = {
        "user_id": user.id,
        "company": body.company_name,
        "role": body.job_title,
        "status": "recruiter_screen",
        "notes": body.notes,
        "comp_range": body.comp_range,
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    resp = supabase_admin.table("pipeline_entries").insert(row).execute()
    entry = resp.data[0] if resp.data else {}
    return JSONResponse({"ok": True, "entry": _entry_to_js(entry) if entry else {}})


@app.get("/calendar/events")
async def calendar_events(user=Depends(get_current_user)):
    conn = (
        supabase_admin.table("gmail_connections")
        .select("refresh_token")
        .eq("user_id", user.id)
        .limit(1)
        .execute()
    )
    if not conn.data or not conn.data[0].get("refresh_token"):
        return JSONResponse({"error": "not_connected"}, status_code=400)
    try:
        access_token = refresh_access_token(conn.data[0]["refresh_token"])
    except Exception:
        return JSONResponse({"error": "token_refresh_failed"}, status_code=401)
    try:
        events = await asyncio.to_thread(fetch_upcoming_events, access_token)
    except Exception as exc:
        logger.exception("Calendar API fetch failed")
        return JSONResponse({"error": str(exc)}, status_code=502)
    return JSONResponse({"events": events})


@app.get("/calendar/event/{event_id}")
async def get_calendar_event(event_id: str, user=Depends(get_current_user)):
    conn = (
        supabase_admin.table("gmail_connections")
        .select("refresh_token")
        .eq("user_id", user.id)
        .limit(1)
        .execute()
    )
    if not conn.data or not conn.data[0].get("refresh_token"):
        return JSONResponse({"error": "not_connected"}, status_code=400)
    try:
        access_token = refresh_access_token(conn.data[0]["refresh_token"])
    except Exception:
        return JSONResponse({"error": "token_refresh_failed"}, status_code=401)
    import requests as _req
    resp = _req.get(
        f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    if not resp.ok:
        return JSONResponse({"error": f"calendar_api_{resp.status_code}"}, status_code=resp.status_code)
    item = resp.json()
    start = item.get("start", {})
    date = (start.get("dateTime") or start.get("date", ""))[:10]
    return JSONResponse({"date": date, "title": item.get("summary", "")})


@app.post("/calendar/create-event")
async def calendar_create_event(request: Request, user=Depends(get_current_user)):
    body = await request.json()
    conn = (
        supabase_admin.table("gmail_connections")
        .select("refresh_token")
        .eq("user_id", user.id)
        .limit(1)
        .execute()
    )
    if not conn.data or not conn.data[0].get("refresh_token"):
        return JSONResponse({"error": "not_connected"}, status_code=400)
    try:
        access_token = refresh_access_token(conn.data[0]["refresh_token"])
    except Exception:
        return JSONResponse({"error": "token_refresh_failed"}, status_code=401)
    try:
        event = await asyncio.to_thread(
            create_calendar_event,
            access_token,
            body.get("title", "Follow-up reminder"),
            body.get("date", ""),
            body.get("description", ""),
        )
    except Exception as exc:
        logger.warning("Calendar event creation failed: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=502)
    return JSONResponse({"event_id": event.get("id", "")})


@app.post("/briefing")
async def briefing(
    job_title: str = Form(...),
    role_level: str = Form(""),
    company_name: str = Form(...),
    company_url: str = Form(""),
    job_description: str = Form(...),
    resume: UploadFile = File(...),
    interviewer_name: str = Form(""),
    interviewer_title: str = Form(""),
    stage_type: str = Form("intro_call"),
    behavioral_focus: str = Form(""),
    tech_assessment_type: str = Form(""),
    tech_topics: str = Form(""),
    roleplay_scenario: str = Form(""),
    roleplay_specifics: str = Form(""),
    panel_makeup: str = Form(""),
    panel_structure: str = Form(""),
    final_trajectory: str = Form(""),
    user=Depends(get_current_user),
):
    global last_submitted_at
    elapsed = time.monotonic() - last_submitted_at
    if elapsed < SUBMIT_COOLDOWN_SECONDS:
        wait_for = round(SUBMIT_COOLDOWN_SECONDS - elapsed)
        return JSONResponse(
            {"error": f"Please wait {wait_for}s before submitting another briefing — this gives the API rate limit time to clear."},
            status_code=429,
        )
    last_submitted_at = time.monotonic()

    resume_text = _extract_resume_text(await resume.read())
    if stage_type not in STAGE_CONTEXT_FIELDS and stage_type != "intro_call":
        stage_type = "intro_call"
    stage_context = _build_stage_context(
        stage_type,
        {
            "behavioral_focus": behavioral_focus,
            "tech_assessment_type": tech_assessment_type,
            "tech_topics": tech_topics,
            "roleplay_scenario": roleplay_scenario,
            "roleplay_specifics": roleplay_specifics,
            "panel_makeup": panel_makeup,
            "panel_structure": panel_structure,
            "final_trajectory": final_trajectory,
        },
    )

    job_id = uuid.uuid4().hex
    jobs[job_id] = {"status": "pending", "stage": "Reading your resume and the job description..."}
    asyncio.create_task(
        _run_briefing_job(
            job_id,
            job_title,
            role_level,
            company_name,
            company_url,
            job_description,
            resume_text,
            interviewer_name,
            interviewer_title,
            stage_type,
            stage_context,
            user.id,
        )
    )

    # Backfill role on matching pipeline entry
    try:
        matches = (
            supabase_admin.table("pipeline_entries")
            .select("id")
            .eq("user_id", user.id)
            .ilike("company", company_name)
            .limit(1)
            .execute()
        )
        if matches.data:
            supabase_admin.table("pipeline_entries").update({"role": job_title}).eq("id", matches.data[0]["id"]).execute()
    except Exception:
        pass

    return JSONResponse({"job_id": job_id})


@app.post("/briefing/sample")
async def briefing_sample(user=Depends(get_current_user_optional)):
    job_id = uuid.uuid4().hex
    jobs[job_id] = {"status": "pending", "stage": SAMPLE_STAGES[0]}
    asyncio.create_task(_run_sample_job(job_id, user.id if user else None))
    return JSONResponse({"job_id": job_id})


@app.get("/briefings")
async def list_briefings(user=Depends(get_current_user)):
    response = (
        supabase_admin.table("briefings")
        .select("id, title, company_name, job_title, stage_type, is_sample, created_at")
        .eq("user_id", user.id)
        .order("created_at", desc=True)
        .execute()
    )
    return JSONResponse({"briefings": response.data})


@app.delete("/briefings/{briefing_id}")
async def delete_briefing(briefing_id: str, user=Depends(get_current_user)):
    supabase_admin.table("briefings").delete().eq("id", briefing_id).eq("user_id", user.id).execute()
    return JSONResponse({"ok": True})


@app.get("/briefings/{briefing_id}/report.pdf")
async def saved_briefing_report(briefing_id: str, user=Depends(get_current_user_for_download)):
    response = (
        supabase_admin.table("briefings")
        .select("company_name, job_title, stage_type, result")
        .eq("id", briefing_id)
        .eq("user_id", user.id)
        .limit(1)
        .execute()
    )
    if not response.data:
        return JSONResponse({"error": "That briefing wasn't found."}, status_code=404)

    row = response.data[0]
    pdf_bytes = pdf_report.generate_pdf(
        row["company_name"], row["job_title"], row["result"], row.get("stage_type", "intro_call")
    )
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "-", row["company_name"]).strip("-") or "briefing"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}-briefing.pdf"'},
    )


@app.get("/briefing/{job_id}/status")
async def briefing_status(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        return JSONResponse({"error": "That briefing wasn't found."}, status_code=404)
    return JSONResponse(
        {
            "status": job["status"],
            "stage": job.get("stage"),
            "result": job.get("result"),
            "error": job.get("error"),
        }
    )


@app.get("/briefing/{job_id}/report.pdf")
async def briefing_report(job_id: str):
    job = jobs.get(job_id)
    if job is None or job["status"] != "done":
        return JSONResponse({"error": "That briefing isn't ready yet."}, status_code=404)

    pdf_bytes = pdf_report.generate_pdf(
        job["company_name"], job["job_title"], job["result"], job.get("stage_type", "intro_call")
    )
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "-", job["company_name"]).strip("-") or "briefing"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}-briefing.pdf"'},
    )


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

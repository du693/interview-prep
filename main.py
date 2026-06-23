import asyncio
import io
import logging
import re
import time
import uuid

import uvicorn
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pypdf import PdfReader

import pdf_report
from agents import researcher, scraper, synthesizer
from sample_briefing import SAMPLE_COMPANY_NAME, SAMPLE_JOB_TITLE, SAMPLE_RESULT, SAMPLE_STAGES

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
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
        )
        jobs[job_id] = {
            "status": "done",
            "result": result,
            "company_name": company_name,
            "job_title": job_title,
        }
    except Exception as exc:
        logger.exception("Briefing job %s failed", job_id)
        jobs[job_id] = {"status": "error", "error": str(exc)}


async def _run_sample_job(job_id: str):
    for stage in SAMPLE_STAGES:
        jobs[job_id]["stage"] = stage
        await asyncio.sleep(1)
    jobs[job_id] = {
        "status": "done",
        "result": SAMPLE_RESULT,
        "company_name": SAMPLE_COMPANY_NAME,
        "job_title": SAMPLE_JOB_TITLE,
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


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
        )
    )

    return JSONResponse({"job_id": job_id})


@app.post("/briefing/sample")
async def briefing_sample():
    job_id = uuid.uuid4().hex
    jobs[job_id] = {"status": "pending", "stage": SAMPLE_STAGES[0]}
    asyncio.create_task(_run_sample_job(job_id))
    return JSONResponse({"job_id": job_id})


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

    pdf_bytes = pdf_report.generate_pdf(job["company_name"], job["job_title"], job["result"])
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "-", job["company_name"]).strip("-") or "briefing"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}-briefing.pdf"'},
    )


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

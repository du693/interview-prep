from dotenv import load_dotenv
import logging
import os
import anthropic

from agents.cost import log_cost

load_dotenv()

logger = logging.getLogger("uvicorn.error")
client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"), max_retries=0)


async def research(company_name: str, job_title: str, interviewer_name: str = "", interviewer_title: str = "") -> str:
    interviewer_line = ""
    if interviewer_name:
        interviewer_line = (
            f"\nThe candidate is interviewing with {interviewer_name}"
            f"{f' ({interviewer_title})' if interviewer_title else ''}. "
            "Search for this person's professional background and role at the company."
        )

    prompt = (
        f"Research {company_name} for a candidate interviewing for a {job_title} role.\n"
        "Search for and summarize:\n"
        "- Recent news and press coverage\n"
        "- Funding history / financial situation (if applicable)\n"
        "- Glassdoor reviews and general employee sentiment\n"
        "- LinkedIn presence: company size, growth trends\n"
        f"{interviewer_line}\n"
        "Write a concise plain-text findings summary, grouped under short headers. "
        "Note clearly where you couldn't find reliable information instead of guessing."
    )

    try:
        message = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            tools=[{
                "type": "web_search_20260209",
                "name": "web_search",
                "max_uses": 1,
                "allowed_callers": ["direct"],
            }],
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError:
        logger.exception("Researcher API call failed")
        return "Live web research was unavailable for this run."

    log_cost("researcher", "claude-haiku-4-5-20251001", message.usage)
    return "\n".join(block.text for block in message.content if block.type == "text")

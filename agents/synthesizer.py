from dotenv import load_dotenv
import os
import anthropic

load_dotenv()

client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"), max_retries=0)

BRIEFING_TOOL = {
    "name": "submit_briefing",
    "description": "Submit the completed interview prep briefing.",
    "input_schema": {
        "type": "object",
        "properties": {
            "candidate_profile": {
                "type": "string",
                "description": "What the hiring manager is looking for in a candidate, grounded in the job description and informed by how the resume lines up.",
            },
            "culture": {"type": "string"},
            "experience_level": {"type": "string"},
            "environment": {
                "type": "string",
                "description": "Pace, company stage, remote/hybrid/onsite, team structure.",
            },
            "company_explainer": {
                "type": "string",
                "description": "Plain-language explanation of what the company/product/industry actually is.",
            },
            "locations": {
                "type": "string",
                "description": "Where the company and this specific role are based.",
            },
            "questions_to_ask": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 4,
                "description": "2-4 strong, specific questions the candidate should ask.",
            },
        },
        "required": [
            "candidate_profile",
            "culture",
            "experience_level",
            "environment",
            "company_explainer",
            "locations",
            "questions_to_ask",
        ],
    },
}

SYSTEM_PROMPT = (
    "You are preparing a candidate for an intro call interview. Ground every claim in the "
    "job description, resume, and research/scrape findings provided to you. If the research "
    "is thin on a topic, say so explicitly rather than inventing specifics.\n\n"
    "Be direct. Every section is 2-3 sentences, plain language, no jargon. Lead with the "
    "point — no \"It's worth noting,\" no \"That said,\" no throat-clearing. State things "
    "plainly and move on. Cut any sentence that doesn't teach the candidate something new."
)


async def synthesize(
    job_title: str,
    role_level: str,
    company_name: str,
    job_description: str,
    resume: str,
    interviewer_name: str,
    interviewer_title: str,
    research_findings: str,
    scrape_findings: str,
) -> dict:
    interviewer_line = (
        f"Interviewing with: {interviewer_name} ({interviewer_title})\n"
        if interviewer_name
        else ""
    )

    prompt = (
        f"Company: {company_name}\n"
        f"Role: {job_title}{f' ({role_level})' if role_level else ''}\n"
        f"{interviewer_line}\n"
        f"--- Job Description ---\n{job_description}\n\n"
        f"--- Candidate Resume ---\n{resume}\n\n"
        f"--- Web Research Findings ---\n{research_findings}\n\n"
        f"--- Company Website Scrape ---\n{scrape_findings}\n\n"
        "Call submit_briefing with the completed interview prep briefing."
    )

    message = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        tools=[BRIEFING_TOOL],
        tool_choice={"type": "tool", "name": "submit_briefing"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in message.content:
        if block.type == "tool_use" and block.name == "submit_briefing":
            return block.input

    raise RuntimeError("Synthesizer did not return a briefing.")

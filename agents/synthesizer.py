from dotenv import load_dotenv
import os
import anthropic

from agents.cost import log_cost

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
                "description": "What the hiring manager is looking for, addressed to the candidate as \"you\" — grounded in the job description and how their resume specifically lines up.",
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
            "role_questions": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 3,
                "description": (
                    "2-3 solid, fundamental questions about the role itself — ramp, team "
                    "structure, what success looks like, day-to-day workflow. Good questions, "
                    "but they could reasonably apply to a similar role at another company."
                ),
            },
            "research_questions": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 3,
                "description": (
                    "2-3 sharp questions, each anchored to a specific, concrete detail pulled "
                    "from the web research findings or company website scrape — a product "
                    "launch, a stated value, recent news, a funding event, a Glassdoor theme, "
                    "the interviewer's background. These should be impossible to ask about a "
                    "different company; that's what proves you did the research."
                ),
            },
        },
        "required": [
            "candidate_profile",
            "culture",
            "experience_level",
            "environment",
            "company_explainer",
            "locations",
            "role_questions",
            "research_questions",
        ],
    },
}

SYSTEM_PROMPT = (
    "You are preparing a candidate for an intro call interview. Write directly to them in "
    "second person — \"you,\" \"your resume,\" \"your background\" — never \"the candidate\" "
    "or third person. Ground every claim in the job description, resume, and research/scrape "
    "findings provided to you. If the research is thin on a topic, say so explicitly rather "
    "than inventing specifics.\n\n"
    "Be direct. Every section is 2-3 sentences, plain language, no jargon. Lead with the "
    "point — no \"It's worth noting,\" no \"That said,\" no throat-clearing. State things "
    "plainly and move on. Cut any sentence that doesn't teach you something new.\n\n"
    "You produce two distinct sets of questions. role_questions are solid, fundamental "
    "questions about the role and team that a well-prepared candidate would ask regardless "
    "of company. research_questions must be genuinely creative and specific — skim the web "
    "research and company site scrape for something concrete (a recent launch, a stated "
    "value, a funding event, a Glassdoor theme, a detail about the interviewer's background) "
    "and build each question around it. A research_question that could be asked verbatim at a "
    "different company is a failure. If the research genuinely turned up nothing usable, say "
    "so in research_questions rather than forcing a fact that isn't there."
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

    log_cost("synthesizer", "claude-sonnet-4-6", message.usage)

    for block in message.content:
        if block.type == "tool_use" and block.name == "submit_briefing":
            return block.input

    raise RuntimeError("Synthesizer did not return a briefing.")

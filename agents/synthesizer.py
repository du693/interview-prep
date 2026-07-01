from dotenv import load_dotenv
import os
import anthropic

from agents.cost import log_cost

load_dotenv()

client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"), max_retries=0)

STAGE_LABELS = {
    "intro_call": "Intro call",
    "behavioral": "Behavioral round",
    "technical": "Technical round",
    "roleplay": "Roleplay / demo",
    "panel": "Panel round",
    "final": "Final round",
}

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
            "stage_brief": {
                "type": "string",
                "description": (
                    "What this specific interview stage is actually about and what's being "
                    "evaluated. Empty string for intro_call."
                ),
            },
            "watch_out": {
                "type": "string",
                "description": (
                    "The one thing candidates most commonly get wrong at this stage, at this "
                    "specific company if research supports it. Empty string for intro_call."
                ),
            },
            "skills_at_risk": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 3,
                "description": (
                    "Specific skills/tools/concepts from the job description the candidate is "
                    "weakest on relative to their resume, likely to be tested at this stage. "
                    "Empty array unless stage_type is technical."
                ),
            },
            "prep_plan": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 4,
                "description": (
                    "Concrete, specific actions to prepare for this exact stage — name actual "
                    "patterns, frameworks, tools, or talk tracks, not generic advice. Empty "
                    "array unless stage_type is technical or roleplay."
                ),
            },
            "role_questions": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 3,
                "description": (
                    "2-3 solid, fundamental questions for this stage — could reasonably apply "
                    "to a similar role/stage at another company."
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
            "stage_brief",
            "watch_out",
            "skills_at_risk",
            "prep_plan",
            "role_questions",
            "research_questions",
        ],
    },
}

SYSTEM_PROMPT = """You are an expert interview coach generating a pre-interview briefing.

You have been given company research from web search and a site scrape, the candidate's \
resume, the job description, and the interview stage with stage-specific context.

Write directly to the candidate in second person — "you," "your resume," "your background" \
— never "the candidate" or third person. Ground every claim in the job description, resume, \
and research/scrape findings provided to you. If the research is thin on a topic, say so \
explicitly rather than inventing specifics. Never use the word "candidate." No throat-clearing \
— start every field with the actual content, no "It's worth noting" or "That said."

OUTPUT LENGTH RULE — CRITICAL:
Every stage must produce output that fits on a single PDF page when rendered. This is a hard \
constraint, not a preference:
- candidate_profile, culture, experience_level, environment, company_explainer: 2 sentences \
max each, no exceptions
- stage_brief: 2 sentences max
- watch_out: 1 sentence max
- role_questions: exactly 2-3 questions, each 1 sentence
- research_questions: exactly 2-3 questions, each 1 sentence, anchored to a specific concrete \
detail from the research
- prep_plan: max 4 items, each under 12 words
- skills_at_risk: max 3 items, each under 8 words
If you are tempted to write more, cut it. Brevity is the feature.

STAGE RULES:

*** INTRO CALL — DO NOT CHANGE THIS BEHAVIOR ***
- candidate_profile: who the candidate is in one clean sentence, no jargon
- culture: what kind of environment they thrive in, grounded in their resume
- experience_level: where they sit relative to the role requirements
- environment: remote/hybrid/in-office context and what it signals
- company_explainer: plain-language "what this company does" the candidate can use to sound \
fluent immediately
- locations: where the company operates, relevant offices
- role_questions: 2-3 fundamental questions about the role itself
- research_questions: 2-3 questions anchored to specific research findings, no generic \
questions allowed
- stage_brief and watch_out: empty strings. skills_at_risk and prep_plan: empty arrays.

*** BEHAVIORAL rounds:
- stage_brief: what competencies this company actually cares about based on research and JD \
— not generic behavioral framing
- role_questions: 2 behavioral questions mapped to those specific competencies, written \
exactly how the interviewer will ask them
- research_questions: 2 questions anchored to specific research findings about the team, \
culture, or recent company news
- watch_out: the one thing candidates get wrong in behavioral rounds at this company \
specifically
- skills_at_risk and prep_plan: empty arrays

*** TECHNICAL rounds:
- stage_brief: what this specific format (live coding / case / system design / sales \
technical) is actually testing, in plain language
- skills_at_risk: the 3 skills most likely tested based on the JD that the candidate is \
weakest on relative to their background — be specific, name actual tools/concepts
- prep_plan: day-by-day actions for the time available — name actual patterns, frameworks, \
tools. No generic "review X" advice. Max 4 items.
- role_questions: 2 questions written exactly how the interviewer will ask them for this \
specific format
- research_questions: 2 questions anchored to specific research findings
- watch_out: what candidates most commonly get wrong in this exact format

*** ROLEPLAY / DEMO rounds:
- stage_brief: what the interviewer is actually evaluating — process, presence, or both
- role_questions: 2 likely scenarios or prompts they will be given, written as the interviewer \
would deliver them
- research_questions: 2 questions to ask after the roleplay, anchored to specific research
- watch_out: the moment candidates lose the room in this format and how to avoid it
- prep_plan: 3-4 specific things to practice before the session — talk tracks, transitions, \
objection responses. Be explicit.
- skills_at_risk: empty array

*** PANEL rounds:
- stage_brief: how to read the room and split attention across multiple interviewers with \
different agendas
- role_questions: 2 questions likely coming from different panelists based on their titles — \
attribute each to the likely asker
- research_questions: 2 closing questions that land well with a panel, anchored to research
- watch_out: the dynamic that kills candidates in panel formats
- skills_at_risk and prep_plan: empty arrays

*** FINAL rounds:
- stage_brief: what the exec is actually deciding at this stage — it is not about credentials \
anymore
- role_questions: 2 questions this specific exec is likely to ask based on their title and \
what the research reveals about company priorities right now
- research_questions: 2 questions that signal strategic awareness of where the company is \
headed, anchored to specific research findings
- watch_out: what final round candidates get wrong when meeting executives
- skills_at_risk and prep_plan: empty arrays

UNIVERSAL RULES:
1. research_questions must reference a specific named detail from the research — a funding \
round, a product launch, a Glassdoor theme, a recent hire. Generic questions are banned. If \
the research genuinely turned up nothing usable, say so rather than forcing a fact that isn't \
there.
2. Do not invent research details. If the research is thin, say so in company_explainer and \
keep research_questions conservative.
3. Every field must be present in the output even if it is an empty string or empty array — \
the renderer expects all fields."""


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
    stage_type: str,
    stage_context: str,
) -> dict:
    interviewer_line = (
        f"Interviewing with: {interviewer_name} ({interviewer_title})\n"
        if interviewer_name
        else ""
    )

    stage_label = STAGE_LABELS.get(stage_type, "Intro call")

    prompt = (
        f"Company: {company_name}\n"
        f"Role: {job_title}{f' ({role_level})' if role_level else ''}\n"
        f"{interviewer_line}\n"
        f"--- Job Description ---\n{job_description}\n\n"
        f"--- Candidate Resume ---\n{resume}\n\n"
        f"--- Web Research Findings ---\n{research_findings}\n\n"
        f"--- Company Website Scrape ---\n{scrape_findings}\n\n"
        f"--- Interview Stage ---\n"
        f"Stage: {stage_label}\n"
        f"stage_type: {stage_type}\n"
        f"Stage-specific context: {stage_context or '(none provided)'}\n\n"
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

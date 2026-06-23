# Interview Prep

A small tool that does the annoying research part before an interview for you. You give it the job title, the job description, your resume, the company, and (optionally) who you're meeting with. It hands back a short briefing covering what the hiring manager is actually looking for, the culture, the experience level expected, what the company does in plain terms, where things are based, and a few solid questions to ask. You can also download it as a one page PDF.

It's built as a 3 agent setup instead of one big prompt, because the data sources are genuinely different and two of them can run at the same time.

## How it's put together

**Agent 1, researcher (`agents/researcher.py`)**
Runs on Haiku with Claude's hosted web search tool. Looks up recent news, funding, Glassdoor sentiment, LinkedIn presence, and info on the interviewer if you gave a name.

**Agent 2, scraper (`agents/scraper.py`)**
No API call at all. Just `requests` and BeautifulSoup pulling the company's about/culture/team pages directly.

**Agent 3, synthesizer (`agents/synthesizer.py`)**
Runs on Sonnet. Takes the job description, your resume, and whatever agents 1 and 2 found, and forces a structured JSON briefing out of it using tool calling so the output is consistent every time.

Agent 1 and Agent 2 run in parallel since they're pulling from two unrelated sources. Agent 3 waits for both, then writes the final briefing.

The web app itself is FastAPI with a single page frontend (vanilla JS, no framework). Submitting kicks off a background job, the page polls a status endpoint and shows a staged "researching, writing" indicator, then types the result out once it's ready.

## Roadblocks I ran into building this

**The web search agent ate way more tokens than I expected.** I assumed a single Sonnet call with a couple of web searches would cost a few thousand tokens. It actually hit over 70,000 tokens in one call, more than double the 30,000 input tokens per minute limit on a Tier 1 account. That's what was actually blowing up the rate limit, not the synthesizer or anything obvious.

**The SDK retries made failures take forever to show up.** By default the Anthropic client retries on a 429 with backoff, so a failed request could sit there for 7 to 8 minutes before finally surfacing the error. Set `max_retries=0` on the client so failures show up in seconds instead, which made debugging this whole thing way less painful.

**Rate limits are tracked per model, not per account.** Once I figured that out, the actual fix was moving the researcher agent from Sonnet to Haiku. Haiku has its own separate token budget, so research and synthesis stopped fighting over the same 30k bucket. That fixed the rate limit problem for good, way more than just trimming prompt sizes did.

**A library version change broke things in a confusing way.** Starlette changed `TemplateResponse` from `(name, context)` to `(request, name, context)` at some point. My old call signature silently passed a dict where a template name was expected, which threw an "unhashable type: dict" error that took a minute to trace back to the actual cause.

**Ran out of API credits mid testing**, which throws a completely different error (400, insufficient balance) than a rate limit (429). They look similar in the moment but mean different things, so don't assume it's always the rate limit if you see an error.

There's also a 90 second cooldown built into the app between submissions, mostly as a guardrail from all of the above.

## Setting up your own API key

If you want to run this yourself with real data instead of the sample mode:

1. Go to [console.anthropic.com](https://console.anthropic.com) and create an account if you don't have one.
2. Go to **Settings > API Keys** and create a new key.
3. Add a small amount of credit under **Plans & Billing**. New accounts start at $0 balance and the API will just reject requests until you add some.
4. In the project root, create a file named `.env` with this line:
   ```
   ANTHROPIC_API_KEY=your-key-here
   ```
5. Install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
6. Run it:
   ```bash
   python main.py
   ```
7. Open `http://127.0.0.1:8000` in your browser.

## How much this actually uses per query

Be aware of this before you start clicking around, since rate limits and credits ran out more than once while building this:

- **Researcher (Haiku):** one web search call. Usually cheap, Haiku pricing is low per token and the search itself is capped to a single use.
- **Synthesizer (Sonnet):** a few thousand tokens of input (job description, resume, and research findings are all capped in length before they get sent) plus up to 2048 tokens of output. Still a small, single call.
- A full briefing is normally a couple cheap calls, not the 70k token disaster mentioned above. That was a Sonnet only, uncapped version. With the current setup it should run you a fraction of a cent per briefing, but actual pricing can change, so check [console.anthropic.com/settings/usage](https://console.anthropic.com/settings/usage) after your first couple of runs to see real numbers for your account.
- There's a 90 second cooldown between submissions built into the app, so you can't accidentally spam requests back to back.
- If you just want to see the UI without spending anything, click **"Load a sample briefing"** on the homepage. It runs entirely off canned data with a fake 3 second delay and never touches the API.

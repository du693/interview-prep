from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; InterviewPrepBot/1.0)"}
KEYWORDS = ("about", "mission", "culture", "team", "careers", "story", "who-we-are")
MAX_PAGES = 3
MAX_CHARS_PER_PAGE = 1500


def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    return " ".join(text.split())[:MAX_CHARS_PER_PAGE]


def _find_candidate_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    base_host = urlparse(base_url).netloc
    seen = set()
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True).lower()
        haystack = f"{href.lower()} {text}"
        if not any(keyword in haystack for keyword in KEYWORDS):
            continue
        absolute = urljoin(base_url, href)
        if urlparse(absolute).netloc != base_host or absolute in seen:
            continue
        seen.add(absolute)
        links.append(absolute)
        if len(links) >= MAX_PAGES - 1:
            break
    return links


def scrape(company_url: str) -> str:
    if not company_url:
        return "No company URL was provided."

    try:
        response = requests.get(company_url, headers=HEADERS, timeout=10)
        response.raise_for_status()
    except requests.RequestException:
        return f"Could not reach company site at {company_url}."

    pages = [(company_url, _extract_text(response.text))]
    for link in _find_candidate_links(response.text, company_url):
        try:
            page_response = requests.get(link, headers=HEADERS, timeout=10)
            page_response.raise_for_status()
        except requests.RequestException:
            continue
        pages.append((link, _extract_text(page_response.text)))

    return "\n\n".join(f"=== {url} ===\n{text}" for url, text in pages)

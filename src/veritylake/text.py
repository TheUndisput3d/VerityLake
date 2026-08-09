from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from veritylake.util import digest

EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
INSTRUCTION_PATTERNS = re.compile(
    r"ignore\s+(all\s+)?(previous|prior|system)\s+instructions|"
    r"reveal\s+(the\s+)?(system\s+prompt|api\s+key)|<\|im_start\|>", re.IGNORECASE
)
CHUNKER_VERSION = "words-v1"


def normalize(text: str, redact_emails: bool = True) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = "".join(c for c in text if not unicodedata.category(c).startswith("C") or c in "\n\t")
    text = re.sub(r"\s+", " ", text).strip()
    return EMAIL.sub("[REDACTED_EMAIL]", text) if redact_emails else text


def extract_html(html: str, url: str, adapter: str = "generic", selector: str = "main") -> dict:
    soup = BeautifulSoup(html, "html.parser")
    if adapter == "books":
        links = [urljoin(url, a["href"]) for a in soup.select(".product_pod h3 a[href], .pager .next a[href]")]
        article = soup.select_one("article.product_page")
        title_node = soup.select_one(".product_main h1")
        title = title_node.get_text(" ", strip=True) if title_node else ""
        if article:
            content = [title]
            rating = soup.select_one(".product_main p.star-rating")
            if rating:
                stars = next((x for x in rating.get("class", []) if x != "star-rating"), "Unknown")
                content.append(f"Rating: {stars} out of five stars.")
            for row in article.select("table tr"):
                th, td = row.find("th"), row.find("td")
                if th and td:
                    content.append(f"{th.get_text(' ', strip=True)}: {td.get_text(' ', strip=True)}")
            desc = article.select_one("#product_description")
            if desc:
                paragraph = desc.find_next_sibling("p")
                if paragraph:
                    content.append("Description: " + paragraph.get_text(" ", strip=True))
            return {"title": title, "text": "\n".join(content), "links": links, "is_document": True}
        return {"title": "", "text": soup.get_text(" ", strip=True), "links": links, "is_document": False}
    for node in soup.select("script, style, noscript, nav, header, footer, aside, form"):
        node.decompose()
    region = soup.select_one(selector) or soup.body or soup
    title_node = soup.find("h1") or soup.title
    title = title_node.get_text(" ", strip=True) if title_node else "Untitled"
    links = [urljoin(url, a["href"]) for a in region.select("a[href]")]
    return {"title": title, "text": region.get_text(" ", strip=True), "links": links, "is_document": True}


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    ordinal: int
    title: str
    url: str
    text: str
    char_start: int
    char_end: int
    content_sha256: str
    fetched_at: str
    raw_key: str
    chunker_version: str = CHUNKER_VERSION


def chunk_document(doc: dict, words: int = 220, overlap: int = 35) -> list[dict]:
    if words <= 0 or overlap < 0 or overlap >= words:
        raise ValueError("Require words > overlap >= 0")
    matches = list(re.finditer(r"\S+", doc["text"]))
    chunks = []
    for start in range(0, len(matches), words - overlap):
        end = min(start + words, len(matches))
        left, right = matches[start].start(), matches[end - 1].end()
        text = doc["text"][left:right]
        chunk_id = digest(f"{doc['doc_id']}:{doc['content_sha256']}:{CHUNKER_VERSION}:{words}:{overlap}:{start}")
        chunks.append(asdict(Chunk(chunk_id=chunk_id, doc_id=doc["doc_id"], ordinal=len(chunks),
                                  title=doc["title"], url=doc["url"], text=text,
                                  char_start=left, char_end=right, content_sha256=digest(text),
                                  fetched_at=doc["fetched_at"], raw_key=doc["raw_key"])))
        if end == len(matches):
            break
    return chunks

"""Ingestion: Getnet web pages. clean text snapshot -> chunks -> vector index.

    python -m app.rag.ingest            # build the index from data/kb_pages (offline)
    python -m app.rag.ingest --fetch    # re-download the pages first, then build
"""
import re
import sys
import time
from collections import Counter

import requests
from bs4 import BeautifulSoup
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings

PAGES_DIR = settings.data_dir / "kb_pages"

# Product and editorial pages chosen by hand.
PRODUCT_PAGES = [
    "https://site.getnet.com.br/",
    "https://site.getnet.com.br/todas-as-maquininhas/",
    "https://site.getnet.com.br/maquininha-de-cartao/",
    "https://site.getnet.com.br/melhor-maquininha-para-o-seu-negocio/",
    "https://site.getnet.com.br/ofertas/",
    "https://site.getnet.com.br/taxas/",
    "https://site.getnet.com.br/conta-digital/",
    "https://site.getnet.com.br/crediario/",
    "https://site.getnet.com.br/pix/",
    "https://site.getnet.com.br/pix-na-maquininha-getnet/",
    "https://site.getnet.com.br/link-de-pagamento/",
    "https://site.getnet.com.br/link-de-pagamento-getnet/",
    "https://site.getnet.com.br/pagamentos-pelo-whatsapp/",
    "https://site.getnet.com.br/get-tap/",
    "https://site.getnet.com.br/getcheckout/",
    "https://site.getnet.com.br/quando-vale-a-pena-antecipar-as-suas-vendas-no-cartao/",
    "https://www.getnet.net/en/",
]

SITEMAP = "https://site.getnet.com.br/page-sitemap.xml"
HELP_PREFIX = "https://site.getnet.com.br/get-ajuda"

_HEADERS = {"User-Agent": "Mozilla/5.0 (kb-ingest)"}
_NOISE_TAGS = ["script", "style", "noscript", "nav", "footer", "header", "svg", "form", "iframe"]
_BOILERPLATE_SHARE = 0.3  # a line present on more than 30% of pages is menu or footer text

# Chunks of at most 900 characters.
SPLITTER = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=150)


def discover_sources() -> list[str]:
    urls = list(PRODUCT_PAGES)
    try:
        sitemap = requests.get(SITEMAP, timeout=20, headers=_HEADERS).text
        urls += [u for u in re.findall(r"<loc>(.*?)</loc>", sitemap) if u.startswith(HELP_PREFIX)]
    except requests.RequestException as exc:
        print(f"sitemap unavailable, using product pages only: {exc}")
    return list(dict.fromkeys(urls))


def clean_html(html: str) -> tuple[str, list[str]]:
    """Return (title, visible lines) with scripts and navigation tags removed."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    for tag in soup(_NOISE_TAGS):
        tag.decompose()
    lines = []
    for line in soup.get_text(separator="\n").splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if len(line) > 1 and line not in lines:
            lines.append(line)
    return title, lines


def fetch_pages() -> int:
    """Download every source and save a clean text snapshot."""
    pages = []
    for url in discover_sources():
        try:
            response = requests.get(url, timeout=20, headers=_HEADERS)
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"skip {url}: {exc}")
            continue
        response.encoding = response.apparent_encoding
        pages.append((url, *clean_html(response.text)))
        time.sleep(0.2)

    # Lines repeated across many pages are template text, not content.
    frequency = Counter(line for _, _, lines in pages for line in lines)
    boilerplate = {line for line, n in frequency.items() if n > len(pages) * _BOILERPLATE_SHARE}

    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    for old in PAGES_DIR.glob("*.md"):
        old.unlink()
    seen_bodies = set()
    for url, title, lines in pages:
        body = "\n".join(line for line in lines if line not in boilerplate)
        if len(body) < 200 or body in seen_bodies:  # empty index pages and redirects to the same page
            continue
        seen_bodies.add(body)
        slug = re.sub(r"[^a-z0-9]+", "-", url.split("//")[1].lower()).strip("-")
        (PAGES_DIR / f"{slug}.md").write_text(f"source: {url}\ntitle: {title}\n\n{body}\n", encoding="utf-8")
    return len(seen_bodies)


def load_pages() -> list[dict]:
    pages = []
    for path in sorted(PAGES_DIR.glob("*.md")):
        header, _, body = path.read_text(encoding="utf-8").partition("\n\n")
        meta = dict(line.split(": ", 1) for line in header.splitlines())
        pages.append({"source": meta["source"], "title": meta.get("title", ""), "text": body})
    return pages


def build_index() -> int:
    """Chunk every snapshot page, embed the chunks and store them in Chroma."""
    from app.rag.retriever import embed, get_collection

    ids, documents, metadatas = [], [], []
    for page in load_pages():
        for i, chunk in enumerate(SPLITTER.split_text(page["text"])):
            ids.append(f"{page['source']}#{i}")
            documents.append(chunk)
            metadatas.append({"source": page["source"], "title": page["title"]})

    # Embed each chunk together with its page title
    embeddings = embed([f"{meta['title']}\n{doc}" for doc, meta in zip(documents, metadatas)])
    collection = get_collection(reset=True)
    collection.add(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
    from app.rag.retriever import _keyword_index

    _keyword_index.cache_clear()  # the keyword index is built from the collection
    return len(ids)


if __name__ == "__main__":
    if "--fetch" in sys.argv:
        print(f"saved {fetch_pages()} pages to {PAGES_DIR}")
    print(f"indexed {build_index()} chunks")

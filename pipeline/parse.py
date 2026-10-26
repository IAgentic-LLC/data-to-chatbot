"""Episode 2: turn each kind of raw file into clean text plus a little metadata.
One function per format; `parse()` picks by file extension. Anything we cannot read raises ParseError with a plain reason."""
import csv
import io
import json
import logging
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

from .clean import decode_bytes, normalize, strip_hidden_comments


logging.getLogger("pypdf").setLevel(logging.ERROR)      # corrupt files are expected here; we report them ourselves


class ParseError(Exception):
    pass


@dataclass
class Parsed:
    doc_key: str                 # stable id: source/path, plus #id for files that hold many documents
    title: str
    text: str
    parser: str
    meta: dict = field(default_factory=dict)


FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def parse_markdown(source: str, path: str, data: bytes) -> list[Parsed]:
    raw = decode_bytes(data)
    meta: dict = {}
    m = FRONT_MATTER.match(raw)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        raw = raw[m.end():]
    raw, hidden = strip_hidden_comments(raw)
    if hidden:
        meta["hidden_comments_removed"] = len(hidden)
        meta["hidden_comments"] = [h[:500] for h in hidden]       # kept as evidence for the injection check (episode 4)
    text = normalize(raw)
    if not text:
        raise ParseError("empty file")
    title = next((ln[2:].strip() for ln in text.splitlines() if ln.startswith("# ")), meta.get("title") or path)
    return [Parsed(f"{source}/{path}", title, text, "markdown", meta)]


class _Main(HTMLParser):
    """Keep headings, paragraphs and list items; drop navigation, scripts, styles, cookie banners, footers and sidebars."""
    SKIP_TAGS = {"script", "style", "nav", "header", "footer", "aside", "noscript", "form", "button"}
    VOID = {"br", "img", "meta", "link", "input", "hr"}

    def __init__(self):
        super().__init__()
        self.stack: list[bool] = []     # one entry per open tag: True if that tag starts a skipped region
        self.out: list[str] = []
        self.title = ""
        self._in_title = False
        self._tag = ""

    @property
    def skipping(self) -> bool:
        return any(self.stack)

    def handle_starttag(self, tag, attrs):
        if tag in self.VOID:
            return
        cls = dict(attrs).get("class", "") or ""
        self.stack.append(tag in self.SKIP_TAGS or "cookie" in cls)
        if tag == "title":
            self._in_title = True
        self._tag = tag

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag not in self.VOID and self.stack:
            self.stack.pop()

    def handle_data(self, data):
        if self._in_title:
            self.title += data
            return
        if self.skipping or not data.strip():
            return
        t = data.strip()
        if self._tag == "h1":
            self.out.append(f"# {t}")
        elif self._tag == "h2":
            self.out.append(f"## {t}")
        elif self._tag == "li":
            self.out.append(f"- {t}")
        else:
            self.out.append(t)


def parse_html(source: str, path: str, data: bytes) -> list[Parsed]:
    p = _Main()
    p.feed(decode_bytes(data))
    text = normalize("\n\n".join(p.out))
    if not text:
        raise ParseError("no readable content in page")
    title = next((ln[2:] for ln in text.splitlines() if ln.startswith("# ")), p.title.split("|")[0].strip())
    return [Parsed(f"{source}/{path}", title, text, "html", {"page_title": p.title.strip()})]


def _page_with_headings(page) -> str:
    """Plain extraction loses which lines were headings. A PDF knows the font size of every piece of text, so lines set
    bigger than the body text become '#' (largest) and '##' headings. A heuristic: it works on documents like ours,
    and a PDF that sets headings in body size gets no headings."""
    pieces: list[tuple[float, float, str]] = []          # (y position, font size, text)

    def visit(text, cm, tm, font_dict, font_size):
        if text.strip():
            pieces.append((round(tm[5], 1), round(font_size * abs(tm[0]) if tm[0] else font_size, 1), text))

    page.extract_text(visitor_text=visit)
    if not pieces:
        return ""
    sizes = sorted(s for _, s, _ in pieces)
    body = sizes[len(sizes) // 2]                          # the most typical size is the body text
    top = sizes[-1]
    lines: list[str] = []
    for y, size, text in pieces:
        t = text.strip("\n")
        if size >= body * 1.15 and len(t) < 120:
            lines.append(("# " if size >= top and top > body * 1.4 else "## ") + t.strip())
        else:
            lines.append(t.strip())
    return "\n".join(lines)


def parse_pdf(source: str, path: str, data: bytes) -> list[Parsed]:
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(_page_with_headings(pg) or pg.extract_text() or "") for pg in reader.pages]
    except (PyPdfError, ValueError, KeyError, OSError, TypeError) as e:
        raise ParseError(f"unreadable PDF ({type(e).__name__})") from e
    if not pages:
        raise ParseError("PDF has no pages")
    text = normalize("\n".join(pages))
    if not text:
        raise ParseError("PDF has no text layer (a scan? needs OCR)")
    title = text.splitlines()[0].lstrip("# ").strip()
    return [Parsed(f"{source}/{path}", title, text, "pdf", {"pages": len(pages)})]


def parse_tickets(source: str, path: str, data: bytes) -> list[Parsed]:
    try:
        tickets = json.loads(decode_bytes(data))
    except json.JSONDecodeError as e:
        raise ParseError(f"invalid JSON: {e.msg}") from e
    out = []
    for t in tickets:
        body = normalize(f"{t.get('subject', '')}\n\n{t.get('body', '')}\n\nResolution: {t.get('resolution', '')}")
        if not (t.get("subject") or t.get("body")):
            continue                       # an empty ticket is skipped, not an error
        out.append(Parsed(f"{source}/{path}#{t['id']}", t.get("subject") or t["id"], body, "tickets",
                          {"ticket_id": t["id"], "status": t.get("status"), "created": t.get("created")}))
    if not out:
        raise ParseError("no usable tickets")
    return out


def parse_csv(source: str, path: str, data: bytes) -> list[Parsed]:
    rows = list(csv.DictReader(io.StringIO(decode_bytes(data))))
    if not rows:
        raise ParseError("CSV has no rows")
    lines = [", ".join(f"{k}: {v}" for k, v in r.items()) for r in rows]
    return [Parsed(f"{source}/{path}", path.rsplit(".", 1)[0].replace("_", " ").title(), normalize("\n".join(lines)), "csv", {"rows": len(rows)})]


PARSERS = {".md": parse_markdown, ".txt": parse_markdown, ".html": parse_html, ".htm": parse_html,
           ".pdf": parse_pdf, ".json": parse_tickets, ".csv": parse_csv}


def parse(source: str, path: str, data: bytes) -> list[Parsed]:
    ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
    fn = PARSERS.get(ext)
    if fn is None:
        raise ParseError(f"no parser for '{ext}' files")
    if not data.strip():
        raise ParseError("empty file")
    return fn(source, path, data)

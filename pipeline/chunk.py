"""Episode 5: cut documents into chunks, the pieces the search finds and the model reads.
Why cut at all? A model reads a limited amount, and a search that returns a whole 20-page document for every question is a bad search.
Two strategies, so we can MEASURE which one finds the right pieces instead of guessing:
  section : one chunk per '## ' section (a heading is where the author already decided one idea ends). Long sections are split at paragraph breaks.
  fixed   : a sliding window of N characters, with overlap. Ignores structure. Simple, and often worse."""
import re
from dataclasses import dataclass, field


@dataclass
class Chunk:
    chunk_id: str      # e.g. "refund-policy#limited-drops"; stable as long as the heading is
    doc_key: str       # which curated document it came from
    source: str
    title: str
    section: str
    text: str
    meta: dict = field(default_factory=dict)

    def for_search(self) -> str:
        # The title and heading are put in front, so a chunk still makes sense when read on its own.
        return f"{self.title} > {self.section}\n{self.text}"


def slug(s: str) -> str:
    return "-".join("".join(c.lower() if c.isalnum() else " " for c in s).split())


def doc_stem(doc_key: str) -> tuple[str, str | None]:
    """'wiki/refund-policy.md' -> ('refund-policy', None).   'tickets/t.json#T-1001' -> ('t', 'T-1001')"""
    path, _, frag = doc_key.partition("#")
    name = path.rsplit("/", 1)[-1]
    return (name.rsplit(".", 1)[0] if "." in name else name), (frag or None)


def _split_long(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts, cur = [], ""
    for para in re.split(r"\n\s*\n|\n(?=- |\d+\. )", text):
        if cur and len(cur) + len(para) + 1 > max_chars:
            parts.append(cur.strip())
            cur = ""
        cur += para + "\n"
    if cur.strip():
        parts.append(cur.strip())
    return parts


def chunk_by_section(doc_key: str, source: str, title: str, text: str, max_chars: int = 900, **_) -> list[Chunk]:
    stem, frag = doc_stem(doc_key)
    sections: list[tuple[str, list[str]]] = [(frag or "Overview", [])]
    for line in text.splitlines():
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif line.startswith("# "):
            continue                                   # the title line: already carried in `title`
        else:
            sections[-1][1].append(line)
    out: list[Chunk] = []
    for name, lines in sections:
        body = "\n".join(lines).strip()
        if not body:
            continue
        for i, piece in enumerate(_split_long(body, max_chars)):
            cid = f"{stem}#{slug(name)}" + (f"-{i + 1}" if i else "")
            out.append(Chunk(cid, doc_key, source, title, name, piece))
    return out


def chunk_fixed(doc_key: str, source: str, title: str, text: str, size: int = 400, overlap: int = 80, **_) -> list[Chunk]:
    stem, _frag = doc_stem(doc_key)
    body = "\n".join(ln for ln in text.splitlines() if not ln.startswith("# ")).strip()
    out, start, n = [], 0, 1
    while start < len(body):
        out.append(Chunk(f"{stem}#part-{n}", doc_key, source, title, f"part {n}", body[start:start + size]))
        start += size - overlap
        n += 1
    return out


CHUNKERS = {"section": chunk_by_section, "fixed": chunk_fixed}


def chunk_all(docs, chunker: str = "section") -> list[Chunk]:
    """docs: curated documents with status 'accepted'. Returns chunks with unique ids."""
    fn = CHUNKERS[chunker]
    out: list[Chunk] = []
    seen: set[str] = set()
    for d in docs:
        for c in fn(d.doc_key, d.source, d.title, d.text):
            c.meta = {"doc_date": d.doc_date}
            base, n = c.chunk_id, 1
            while c.chunk_id in seen:                  # two documents produced the same id: keep both, make the id unique
                n += 1
                c.chunk_id = f"{base}~{d.source}" if n == 2 else f"{base}~{d.source}{n}"
            seen.add(c.chunk_id)
            out.append(c)
    return out

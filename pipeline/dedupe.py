"""Episode 4: find documents that say the same thing, and decide which one wins.
Exact copies share a text hash. Near-copies (the same page as HTML and as PDF, or an old and a new version of one policy) are found by
comparing sets of 3-word shingles: the overlap divided by the union is the Jaccard similarity."""
import re
from dataclasses import dataclass

DATE_IN_TEXT = re.compile(r"(?:Last reviewed|Updated|Date(?: of drop)?)\s*[:=]\s*(\d{4}-\d{2}-\d{2})", re.I)
SOURCE_RANK = {"wiki": 0, "web": 1, "pdf": 2, "tickets": 3, "prices": 4, "uploads": 5}   # who we trust most when dates tie


def shingles(text: str, n: int = 3) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {" ".join(words[i:i + n]) for i in range(max(0, len(words) - n + 1))}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def doc_date(text: str, meta: dict) -> str | None:
    """The date a document says it is from: a 'Last reviewed' line in the text, else front matter, else None."""
    m = DATE_IN_TEXT.search(text)
    return m.group(1) if m else (meta.get("updated") or meta.get("created"))


@dataclass
class Item:
    key: str
    source: str
    text: str
    text_sha: str
    date: str | None


def clusters(items: list[Item], threshold: float = 0.8) -> list[list[Item]]:
    """Group items whose shingle overlap with the group's first member is at least `threshold`. Groups of one are returned too."""
    sh = {i.key: shingles(i.text) for i in items}
    groups: list[list[Item]] = []
    for it in sorted(items, key=lambda x: x.key):
        for g in groups:
            if it.text_sha == g[0].text_sha or jaccard(sh[it.key], sh[g[0].key]) >= threshold:
                g.append(it)
                break
        else:
            groups.append([it])
    return groups


def winner(group: list[Item]) -> Item:
    """Newest date wins; if dates tie (or are missing), the more trusted source wins; then the key, so the result is stable."""
    return sorted(group, key=lambda i: (_neg_date(i.date), SOURCE_RANK.get(i.source, 9), i.key))[0]


def _neg_date(d: str | None) -> str:
    # sort newest first: invert each digit so a bigger date sorts earlier; a missing date sorts last
    return "".join(str(9 - int(c)) if c.isdigit() else c for c in d) if d else "z"


def changed_words(old: str, new: str, limit: int = 4) -> list[str]:
    """What actually differs, as 'old -> new' pairs, so a person can see the contradiction (for example '30-day -> 7-day')."""
    import difflib
    a, b = old.split(), new.split()
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != "equal":
            out.append(f"{' '.join(a[i1:i2]) or '(nothing)'} -> {' '.join(b[j1:j2]) or '(nothing)'}")
    return out[:limit]

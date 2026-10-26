"""Episode 2: text cleaning. Pure functions, no files and no database, so each one is easy to test."""
import re
import unicodedata
from collections import Counter

HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
MOJIBAKE_MARKERS = tuple(chr(c).encode("utf-8").decode("cp1252", errors="ignore") for c in (0x2019, 0x2013, 0xe9, 0xe8, 0xe4, 0xf6, 0xfc))


def decode_bytes(data: bytes) -> str:
    """Bytes to text. UTF-8 first (strip a byte-order mark), latin-1 as the last resort so we never crash."""
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")      # Windows line endings -> one kind


def fix_mojibake(text: str) -> str:
    """Repair text that was UTF-8, wrongly decoded as Windows-1252, then saved as UTF-8 again ('donâ€™t' -> 'don't')."""
    if not any(m in text for m in MOJIBAKE_MARKERS):
        return text
    try:
        fixed = text.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    return fixed


def normalize(text: str) -> str:
    text = fix_mojibake(text)
    text = unicodedata.normalize("NFKC", text)          # one canonical form for look-alike characters
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-").replace(" ", " ")
    text = CONTROL.sub("", text)
    text = "\n".join(line.rstrip() for line in text.splitlines())
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_hidden_comments(text: str) -> tuple[str, list[str]]:
    """HTML comments are invisible to a human reader but a model would read them. Remove them, and return what they said
    so episode 4 can check whether they were instructions aimed at the model."""
    found = [c[4:-3].strip() for c in HTML_COMMENT.findall(text)]
    return HTML_COMMENT.sub("", text), found


def find_boilerplate(docs: list[str], min_docs: int = 3, min_share: float = 0.6) -> set[str]:
    """A line that appears in most documents of one feed (a page footer, a banner) is not content.
    Needs at least `min_docs` documents to judge."""
    if len(docs) < min_docs:
        return set()
    counts: Counter = Counter()
    for d in docs:
        counts.update({ln.strip() for ln in d.splitlines() if ln.strip()})
    return {ln for ln, c in counts.items() if c / len(docs) >= min_share}


def remove_lines(text: str, lines: set[str]) -> str:
    if not lines:
        return text
    kept = [ln for ln in text.splitlines() if ln.strip() not in lines]
    return normalize("\n".join(kept))

"""Episode 4: a document is untrusted input. Text inside it can address the model instead of the reader ("ignore your instructions...").
This is a SCREEN, not a defence on its own: a patient attacker can phrase it a hundred other ways. It catches the lazy cases, sends them to a human,
and episode 8 adds the defences that still hold when the screen misses (the model never gets tools or secrets it does not need)."""
import re

PATTERNS = {
    "ignore-instructions": re.compile(r"\b(ignore|disregard|forget)\b[^.\n]{0,40}\b(previous|prior|above|earlier|all)\b[^.\n]{0,30}\b(instructions?|rules?|prompts?)\b", re.I),
    "role-override": re.compile(r"\b(you are now|act as|pretend to be|new instructions?:|system (note|prompt|message))\b", re.I),
    "secret-request": re.compile(r"\b(reveal|share|send|print|output)\b[^.\n]{0,40}\b(password|api key|secret|credentials?|token)\b", re.I),
    "exfiltration": re.compile(r"\b(send|post|upload|forward)\b[^.\n]{0,40}\b(to|at)\b[^.\n]{0,20}(https?://|\w+@\w+)", re.I),
}


def scan(*texts: str) -> list[str]:
    """Names of the patterns that matched anywhere in the given texts."""
    hits: list[str] = []
    for name, rx in PATTERNS.items():
        if any(rx.search(t) for t in texts if t):
            hits.append(name)
    return hits

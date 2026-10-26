"""Episode 4: remove personal data from text before it can be indexed. Replace with a labelled placeholder and count what was removed.
Regexes catch the common shapes (emails, phone numbers). They miss names and addresses: say so out loud; a real project adds a trained detector."""
import re

EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
# Anything that looks like a phone number: optional +, then digits separated by spaces, dots, dashes or brackets.
PHONE = re.compile(r"(?<![\w-])\+?\d[\d ().-]{7,}\d(?![\w-])")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Addresses we publish on purpose (company mailboxes) are not personal data.
KEEP_DOMAINS = ("@dropline.example",)


def scrub(text: str) -> tuple[str, dict]:
    counts = {"email": 0, "phone": 0}

    def email(m):
        if m.group(0).lower().endswith(KEEP_DOMAINS):
            return m.group(0)
        counts["email"] += 1
        return "[EMAIL]"

    def phone(m):
        s = m.group(0)
        digits = re.sub(r"\D", "", s)
        if len(digits) < 9 or DATE.match(s.strip()):    # dates and short ids are not phone numbers
            return s
        counts["phone"] += 1
        return "[PHONE]"

    text = EMAIL.sub(email, text)
    text = PHONE.sub(phone, text)
    return text, {k: v for k, v in counts.items() if v}

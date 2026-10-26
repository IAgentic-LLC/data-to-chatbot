"""Offline tests (no Docker, no network): run with `python -m pytest -q`."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pipeline.clean import decode_bytes, find_boilerplate, fix_mojibake, normalize, remove_lines, strip_hidden_comments
from pipeline.hashing import sha256_bytes
from pipeline.land import land
from pipeline.manifest import MemoryManifest
from pipeline.parse import ParseError, parse
from pipeline.silver import MemorySilver, build_silver
from pipeline.storage import LocalStorage

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def sources(tmp_path_factory):
    """Fresh copy of the messy sources, built by the real generator into a temp folder."""
    out = tmp_path_factory.mktemp("sources")
    code = (ROOT / "scripts" / "generate_sources.py").read_text(encoding="utf-8").replace(
        'OUT = ROOT / "data" / "sources"', f"OUT = Path(r'{out}')")
    script = out.parent / "gen_tmp.py"
    script.write_text(code.replace("ROOT = Path(__file__).resolve().parent.parent", f"ROOT = Path(r'{ROOT}')"), encoding="utf-8")
    subprocess.run([sys.executable, str(script)], check=True, capture_output=True)
    return out


# ---- episode 1: landing -------------------------------------------------------------------------

def test_landing_is_idempotent(sources, tmp_path):
    storage, manifest = LocalStorage(tmp_path / "bronze"), MemoryManifest()
    first = land(sources, storage, manifest, "run-1")
    second = land(sources, storage, manifest, "run-2")
    assert first.new == 21 and first.unchanged == 0           # 21 data files (TRAPS.md is a file too, counted below)
    assert second.new == 0 and second.unchanged == first.new  # nothing repeated
    assert second.stored == 0


def test_identical_bytes_are_stored_once(sources, tmp_path):
    storage, manifest = LocalStorage(tmp_path / "b"), MemoryManifest()
    rep = land(sources, storage, manifest, "r")
    a = next(r for r in manifest.all() if r.path == "refund-policy.md" and r.source == "wiki")
    b = next(r for r in manifest.all() if r.path == "refund-policy-copy.md")
    assert a.sha256 == b.sha256 and a.storage_key == b.storage_key
    assert rep.stored == rep.new - 1                           # exactly one blob saved by the duplicate


def test_changed_file_is_a_new_version_and_old_one_is_kept(sources, tmp_path):
    work = tmp_path / "src"
    shutil.copytree(sources, work)
    storage, manifest = LocalStorage(tmp_path / "b"), MemoryManifest()
    land(work, storage, manifest, "r1")
    f = work / "wiki" / "on-call.md"
    old_sha = sha256_bytes(f.read_bytes())
    f.write_text(f.read_text(encoding="utf-8") + "\nNew line.\n", encoding="utf-8")
    rep = land(work, storage, manifest, "r2")
    assert rep.new == 1
    assert storage.exists(f"blobs/{old_sha[:2]}/{old_sha}")   # bronze never forgets


# ---- episode 2: cleaning and parsing --------------------------------------------------------------

def test_mojibake_repair():
    assert fix_mojibake("We donâ€™t ship") == "We don’t ship"
    assert fix_mojibake("Plain text stays") == "Plain text stays"


def test_decode_handles_bom_and_windows_newlines():
    assert decode_bytes(b"\xef\xbb\xbfa\r\nb") == "a\nb"


def test_normalize_whitespace_and_quotes():
    messy = "  a" + chr(0x2019) + "s   b " + chr(10) * 4 + " c "
    assert normalize(messy) == "a's b" + chr(10) * 2 + " c"   # indentation is kept on purpose (code, nested lists)


def test_hidden_comments_removed_and_counted():
    text, found = strip_hidden_comments("keep <!-- secret --> this")
    assert found == ["secret"] and "secret" not in text


def test_boilerplate_needs_enough_documents():
    docs = [f"Body {i}\nFooter line" for i in range(5)]
    assert find_boilerplate(docs) == {"Footer line"}
    assert find_boilerplate(docs[:2]) == set()                # too few documents to judge
    assert remove_lines("Body 1\nFooter line", {"Footer line"}) == "Body 1"


def test_html_keeps_content_drops_chrome():
    html = (ROOT / "data" / "sources" / "web" / "refund-policy.html")
    if not html.exists():
        pytest.skip("run scripts/generate_sources.py first")
    t = parse("web", "refund-policy.html", html.read_bytes())[0].text
    assert "Standard returns" in t
    for junk in ("cookies", "newsletter", "Sign in", "Careers", "dataLayer"):
        assert junk not in t


def test_rejections_have_reasons():
    with pytest.raises(ParseError, match="empty"):
        parse("uploads", "empty.md", b"")
    with pytest.raises(ParseError, match="unreadable PDF"):
        parse("uploads", "x.pdf", b"%PDF-1.4 broken")
    with pytest.raises(ParseError, match="no parser"):
        parse("uploads", "x.exe", b"MZ")


def test_empty_ticket_is_skipped_not_fatal():
    import json
    data = json.dumps([{"id": "T1", "subject": "a", "body": "b", "resolution": "c"}, {"id": "T2", "subject": "", "body": ""}]).encode()
    docs = parse("tickets", "t.json", data)
    assert [d.doc_key for d in docs] == ["tickets/t.json#T1"]


def test_silver_end_to_end_and_idempotent(sources, tmp_path):
    storage, manifest, silver = LocalStorage(tmp_path / "b"), MemoryManifest(), MemorySilver()
    land(sources, storage, manifest, "r")
    first = build_silver(manifest, storage, silver)
    reasons = {r.path: r.reason for r in silver.rejects()}
    assert reasons["empty.md"] == "empty file"
    assert reasons["scan-corrupt.pdf"].startswith("unreadable PDF")
    texts = {d.doc_key: d.text for d in silver.docs()}
    assert "Ignore all previous instructions" not in texts["uploads/partner-faq.md"]      # hidden comment removed
    assert "Dropline internal - page footer" not in texts["pdf/on-call.pdf"]              # boilerplate removed
    assert "don't ship" in texts["uploads/shipping-notes-mojibake.md"]
    assert "tickets/tickets_2026-05.json#T-1001" in texts and "tickets/tickets_2026-05.json#T-1005" not in texts
    second = build_silver(manifest, storage, silver)
    assert second.parsed == 0 and second.rejected == 0 and second.skipped > 0

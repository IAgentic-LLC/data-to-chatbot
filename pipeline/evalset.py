"""Episode 5 (and 6): measure whether search finds the right pieces. The questions and their right chunks come from the Agentic RAG series' golden set.

Two rules carried over from Part 2:
  * split: 'dev' questions may be looked at and tuned on; 'test' questions are for the final check only. Tuning on the test set makes the score a lie.
  * a chunk 'covers' an expected one when it contains most of the same words in the same order (shared 3-word shingles), so the score does not depend
    on which chunking strategy was used. Otherwise a different chunker could never match an expected id and would always score zero."""
from dataclasses import dataclass, field
from pathlib import Path

from .chunk import chunk_all
from .dedupe import shingles

GOLDEN = Path(__file__).resolve().parent.parent / "data" / "golden" / "golden_v2.yaml"


def load_golden(path: Path = GOLDEN, split: str | None = None, answerable_only: bool = True) -> list[dict]:
    import yaml
    items = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return [i for i in items if (split is None or i.get("split") == split) and (i.get("answerable", True) or not answerable_only)]


def reference_chunks(curated_docs) -> dict[str, str]:
    """The expected ids, as text, taken from the section chunker over the accepted documents."""
    return {c.chunk_id: c.for_search() for c in chunk_all([d for d in curated_docs if d.status == "accepted"], "section")}


def covers(reference_text: str, got_text: str, threshold: float = 0.6) -> bool:
    ref = shingles(reference_text)
    return bool(ref) and len(ref & shingles(got_text)) / len(ref) >= threshold


@dataclass
class EvalReport:
    k: int
    questions: int
    recall: float                 # average share of the expected chunks that were found in the top k
    all_found: float              # share of questions where EVERY expected chunk was found
    misses: list = field(default_factory=list)       # (question id, missing chunk ids)
    skipped: list = field(default_factory=list)      # question ids left out: they ask about documents this corpus does not contain

    def __str__(self):
        extra = f", {len(self.skipped)} skipped (their documents are not in this corpus)" if self.skipped else ""
        return f"recall@{self.k}={self.recall:.2f}  all-found={self.all_found:.2f}  ({self.questions} questions{extra})"


def retrieval_eval(search_fn, golden: list[dict], reference: dict[str, str], k: int = 5) -> EvalReport:
    """search_fn(question, k) -> list of Hit. Returns recall over the golden questions."""
    recalls, full, misses, skipped = [], 0, [], []
    scored = []
    for item in golden:
        if all(e in reference for e in item["expect"]):
            scored.append(item)
        else:
            skipped.append(item["id"])         # scoring these would punish search for a document that simply is not there
    golden = scored
    for item in golden:
        expected = [e for e in item["expect"]]
        hits = search_fn(item["q"], k)
        found, missing = 0, []
        for e in expected:
            ref = reference.get(e)
            if ref and any(covers(ref, h.text if hasattr(h, "text") else h) for h in hits):
                found += 1
            else:
                missing.append(e)
        recalls.append(found / len(expected))
        full += not missing
        if missing:
            misses.append((item["id"], missing))
    n = len(golden)
    return EvalReport(k, n, sum(recalls) / n if n else 0.0, full / n if n else 0.0, misses, skipped)

"""Episode 5: turn text into vectors (lists of numbers) so that texts with similar meaning end up close together.

Two embedders behind one small interface:
  fastembed : a real embedding model (BAAI/bge-small-en-v1.5, 384 numbers per text) that runs on your own computer. Free, no account, no data leaves the machine.
  hash      : a toy that needs nothing installed. It counts word pieces. Good enough to run the tests offline; it does NOT understand meaning, only shared words.
Governance note: because the real one runs locally, the text of your documents is never sent to a third party to be embedded."""
import math
import os
import re
import zlib


class Embedder:
    name = "base"
    dim = 0

    def __init__(self):
        self.texts_embedded = 0          # how many texts this object has actually been asked to embed (what an API would bill you for)

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.texts_embedded += len(texts)
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed_query(text)

    def _embed(self, texts):
        raise NotImplementedError

    def _embed_query(self, text):
        return self._embed([text])[0]


class HashEmbedder(Embedder):
    name = "hash-256"
    dim = 256

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        words = re.findall(r"[a-z0-9]+", text.lower())
        for tok in words + [a + "_" + b for a, b in zip(words, words[1:])]:
            h = zlib.crc32(tok.encode("utf-8"))
            v[h % self.dim] += 1.0 if (h >> 16) & 1 else -1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def _embed(self, texts):
        return [self._vec(t) for t in texts]


class FastEmbedder(Embedder):
    name = "BAAI/bge-small-en-v1.5"
    dim = 384

    def __init__(self):
        super().__init__()
        from fastembed import TextEmbedding
        self.model = TextEmbedding(self.name)            # downloads about 130 MB the first time, then works offline

    def _embed(self, texts):
        return [list(map(float, v)) for v in self.model.embed(texts)]

    def _embed_query(self, text):
        return [float(x) for x in next(iter(self.model.query_embed([text])))]


def get_embedder(name: str | None = None) -> Embedder:
    name = name or os.environ.get("EMBED_PROVIDER", "fastembed")
    if name == "hash":
        return HashEmbedder()
    if name == "fastembed":
        return FastEmbedder()
    raise ValueError(f"unknown embedder '{name}' (use 'fastembed' or 'hash')")

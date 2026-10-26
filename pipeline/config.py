"""All settings come from environment variables, with local-development defaults."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


DATABASE_URL = env("DATABASE_URL", "postgresql://pipeline:pipeline@127.0.0.1:5433/pipeline")
S3_ENDPOINT = env("S3_ENDPOINT", "http://127.0.0.1:8333")
S3_ACCESS_KEY = env("S3_ACCESS_KEY", "pipeline")
S3_SECRET_KEY = env("S3_SECRET_KEY", "pipeline-secret")
S3_BUCKET = env("S3_BUCKET", "bronze")
SOURCES_DIR = Path(env("SOURCES_DIR", str(ROOT / "data" / "sources")))

# Episode 5B: the knowledge graph (Neo4j). The password below is a throwaway for your own machine; episode 9 reads a real one from a secret.
NEO4J_URI = env("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = env("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = env("NEO4J_PASSWORD", "dropline-local-pw")
GRAPH_ENABLED = env("GRAPH_ENABLED", "0") == "1"      # the Airflow DAG adds the graph task only when this is 1 (episode 5B turns it on)

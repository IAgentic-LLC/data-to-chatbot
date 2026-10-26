"""Episode 4: the ELT half of the course. Here the transformation is SQL running INSIDE the database, over data that was already loaded.
(The Python steps before this are the ETL half: parse and clean happen before anything is stored as silver.)
Views are saved queries: nothing is copied, they always show the current tables."""

VIEWS = """
-- how many documents ended in each status, and how much text that is
CREATE OR REPLACE VIEW v_curation_summary AS
SELECT status, count(*) AS docs, coalesce(sum(length(text)), 0) AS chars
FROM curated_docs GROUP BY status ORDER BY status;

-- documents waiting for a human decision
CREATE OR REPLACE VIEW v_review_queue AS
SELECT c.doc_key, c.reason
FROM curated_docs c
WHERE c.status = 'quarantined' AND NOT EXISTS (SELECT 1 FROM curation_decisions d WHERE d.doc_key = c.doc_key);

-- lineage: every curated document back to the exact raw file and the pipeline run that brought it in
CREATE OR REPLACE VIEW v_lineage AS
SELECT c.doc_key, c.status, b.run_id, b.fetched_at, b.sha256 AS raw_sha256, b.storage_key
FROM curated_docs c
JOIN bronze_files b ON b.source = c.source AND b.path = c.path AND b.sha256 = c.bronze_sha256;

-- the documents the search index is built from
CREATE OR REPLACE VIEW v_searchable_docs AS
SELECT doc_key, source, title, text, doc_date FROM curated_docs WHERE status = 'accepted';
"""


def install_views(conn) -> None:
    conn.execute(VIEWS)

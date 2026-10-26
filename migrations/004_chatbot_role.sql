-- Governance: least privilege. The chatbot gets its own database login that can read the search index and NOTHING else.
-- It cannot see raw files, silver text, curation records, tickets or the audit log. (Each chunks_vN table is granted when it is built.)
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'chatbot_ro') THEN
    CREATE ROLE chatbot_ro NOLOGIN;      -- no password stored in a migration; 'grant-chatbot' sets one at deploy time
  END IF;
END $$;
GRANT SELECT ON index_versions, index_alias TO chatbot_ro;

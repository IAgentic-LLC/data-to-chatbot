-- A build that crashes must not look like it is still running. Add the status 'failed'.
-- (We did NOT edit 003: it was already applied. Changing a table that exists means a new numbered file.)
ALTER TABLE index_versions DROP CONSTRAINT IF EXISTS index_versions_status_check;
ALTER TABLE index_versions ADD CONSTRAINT index_versions_status_check CHECK (status IN ('building', 'ready', 'live', 'retired', 'failed'));

-- Cases are the primary record: a case owns its documents, its people and its summary.
-- Extends the supplied schema in place; no existing row is replaced.

-- A case needs a human-readable handle of its own, independent of the FIR number.
ALTER TABLE cases ADD COLUMN IF NOT EXISTS title TEXT;
-- Registered/filed date, distinct from case_month, so retrieval can order by when the case opened.
ALTER TABLE cases ADD COLUMN IF NOT EXISTS opened_on DATE;
-- The generated case summary, stored whole: {sections, sources, coverage, retrievalMode}.
ALTER TABLE cases ADD COLUMN IF NOT EXISTS summary JSONB;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS summary_language TEXT;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS summary_generated_at TIMESTAMPTZ;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS summary_generated_by INTEGER REFERENCES officers(officer_id);

CREATE INDEX IF NOT EXISTS cases_status_idx ON cases(case_status);
CREATE INDEX IF NOT EXISTS cases_month_idx ON cases(case_month DESC);

-- Which documents evidence a case. Derived from the reviewed extraction, so a case
-- gains its sources when an officer confirms a document, never before.
-- Dropped first, not replaced: CREATE OR REPLACE VIEW cannot add a column anywhere but the
-- end of the list, so replacing an older definition in place fails. The view holds no data.
DROP VIEW IF EXISTS case_documents;
CREATE VIEW case_documents AS
SELECT DISTINCT e.canonical_id AS case_id, d.document_id, d.officer_id,
       d.original_name, d.mime_type, d.source_type, d.uploaded_at, d.confirmed_at
FROM extracted_entities e
JOIN officer_documents d ON d.document_id = e.document_id
WHERE e.kind = 'Case' AND d.confirmed_at IS NOT NULL;

-- Per-officer "currently working on" state, keyed by case instead of by person.
-- The person-keyed tables (officer_pinned_criminal, officer_working_list) are left in
-- place so existing rows survive; nothing reads them now that browsing is case-first.
CREATE TABLE IF NOT EXISTS officer_pinned_case (
  officer_id INTEGER PRIMARY KEY REFERENCES officers(officer_id) ON DELETE CASCADE,
  case_id    VARCHAR(20) NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
  pinned_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS officer_case_list (
  officer_id INTEGER NOT NULL REFERENCES officers(officer_id) ON DELETE CASCADE,
  case_id    VARCHAR(20) NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
  added_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (officer_id, case_id)
);

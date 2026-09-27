--
-- Sample database export for the Upload page's "Database export" source type.
-- SYNTHETIC DATA — every person, case, address and number below is fictional.
--
-- Upload this file on the Upload page with source "Database export (SQL dump, SQLite, CSV, JSON)".
-- The backend reads the rows as data and stages them for review; no statement here is executed.
-- Produce a comparable file from a real database with:
--   pg_dump --format=plain --column-inserts -d yourdb -f export.sql
--

INSERT INTO crime_types (crime_id, crime_name, description) VALUES
  (1, 'Theft', 'Taking property without consent.'),
  (2, 'Financial fraud', 'Deception carried out for financial gain.');

INSERT INTO locations (location_id, city, state) VALUES
  (1, 'Nandipur', 'Maharashtra'),
  (2, 'Vashi', 'Maharashtra'),
  (3, 'Bengaluru', 'Karnataka');

INSERT INTO organizations (organization_id, organization_name, city) VALUES
  (1, 'Harbour View Police Station', 'Nandipur'),
  (2, 'Meridian Electronics', 'Nandipur');

INSERT INTO vehicles (vehicle_id, registration, description) VALUES
  (1, 'MH12AB4521', 'Black motorcycle, synthetic record.');

INSERT INTO persons (person_id, name, alias, dob, age, city, state, phone, record_status) VALUES
  ('P001', 'Rohan Mehta', 'Ronny', '1997-04-02', 29, 'Nandipur', 'Maharashtra', '9876501234', 'Extracted (unverified)'),
  ('P002', 'Sameer Qureshi', NULL, '1995-11-18', 31, 'Nandipur', 'Maharashtra', '9876509876', 'Extracted (unverified)'),
  ('P003', 'Kavita Rao', NULL, NULL, 27, 'Nandipur', 'Maharashtra', NULL, 'Extracted (unverified)'),
  ('P004', 'Arjun Deshmukh', NULL, '1992-01-09', 34, 'Nandipur', 'Maharashtra', '9876512345', 'Extracted (unverified)'),
  ('P005', 'Deepa Menon', 'Dee', NULL, 38, 'Bengaluru', 'Karnataka', NULL, 'Extracted (unverified)');

INSERT INTO cases (case_id, crime_id, location_id, case_status, case_month) VALUES
  ('FIR-SYN-2026-0142', 1, 1, 'Under investigation', '2026-06-01'),
  ('FIR-SYN-2026-0198', 2, 2, 'Under investigation', '2026-07-01');

-- A join table: each row links a person to a case with the role recorded in the source.
COPY case_people (case_id, person_id, role) FROM stdin;
FIR-SYN-2026-0142	P001	suspect
FIR-SYN-2026-0142	P002	suspect
FIR-SYN-2026-0142	P003	witness
FIR-SYN-2026-0142	P004	complainant
FIR-SYN-2026-0198	P001	accused
FIR-SYN-2026-0198	P005	witness
\.

-- END OF SYNTHETIC SAMPLE

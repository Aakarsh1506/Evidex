--
-- Second sample database export: a cyber-crime unit's own schema.
-- SYNTHETIC DATA — every person, firm, number and case below is fictional.
--
-- Deliberately unlike docs/sample_50_criminals.sql: different table and column names
-- (suspects/full_name, fir_records/fir_no, offences, places, firms), MySQL-style backticks,
-- and a COPY block that takes its column names from the CREATE TABLE above it.
--
-- Upload on the Upload page with source "Database export (SQL dump, SQLite, CSV, JSON)".
-- Rows are read as data and staged for review; no statement here is executed.
--

CREATE TABLE `suspects` (
  `suspect_id` varchar(12) NOT NULL,
  `full_name` varchar(120) NOT NULL,
  `aka` varchar(60),
  `birth_date` date,
  `age` int,
  `town` varchar(80),
  `province` varchar(80),
  `mobile` varchar(20),
  PRIMARY KEY (`suspect_id`)
);

CREATE TABLE `offences` (`offence_id` int, `offence` varchar(80));
CREATE TABLE `places` (`place_id` int, `city` varchar(80), `state` varchar(80));
CREATE TABLE `firms` (`firm_id` int, `company_name` varchar(120), `city` varchar(80));
CREATE TABLE `fir_records` (`fir_no` varchar(30), `offence_id` int, `place_id` int, `case_status` varchar(40), `case_month` date);
CREATE TABLE `fir_people` (`fir_no` varchar(30), `suspect_id` varchar(12), `relation` varchar(30));

INSERT INTO `offences` (`offence_id`, `offence`) VALUES
  (11, 'Cyber fraud'),
  (12, 'Identity theft'),
  (13, 'Money laundering');

INSERT INTO `places` (`place_id`, `city`, `state`) VALUES
  (21, 'Bengaluru', 'Karnataka'),
  (22, 'Whitefield', 'Karnataka'),
  (23, 'Hyderabad', 'Telangana');

INSERT INTO `firms` (`firm_id`, `company_name`, `city`) VALUES
  (31, 'Apex Finserv Private Limited', 'Bengaluru'),
  (32, 'Silverline Payments LLP', 'Hyderabad');

-- pg_dump --column-inserts style, without backticks, mixed into the same file.
INSERT INTO suspects (suspect_id, full_name, aka, birth_date, age, town, province, mobile) VALUES
  ('CY-01', 'Farhan Ali', 'Fizz', '1994-03-11', 32, 'Bengaluru', 'Karnataka', '9845012345'),
  ('CY-02', 'Lakshmi Reddy', NULL, '1988-07-29', 38, 'Whitefield', 'Karnataka', '9900112233'),
  ('CY-03', 'Suresh Gowda', NULL, '1991-12-04', 34, 'Bengaluru', 'Karnataka', '9845067890'),
  ('CY-04', 'Deepa Menon', 'Dee', '1985-05-20', 41, 'Hyderabad', 'Telangana', '9701234567'),
  ('CY-05', 'Imran Qureshi', NULL, '1996-09-02', 30, 'Hyderabad', 'Telangana', '9701987654');

INSERT INTO fir_records (fir_no, offence_id, place_id, case_status, case_month) VALUES
  ('FIR-CY-2026-071', 11, 21, 'Under investigation', '2026-04-01'),
  ('FIR-CY-2026-084', 12, 22, 'Under investigation', '2026-05-01'),
  ('FIR-CY-2026-099', 13, 23, 'Charge sheet filed', '2026-06-01');

-- Column names for this COPY come from the CREATE TABLE above.
COPY fir_people FROM stdin;
FIR-CY-2026-071	CY-01	accused
FIR-CY-2026-071	CY-03	witness
FIR-CY-2026-084	CY-01	suspect
FIR-CY-2026-084	CY-02	complainant
FIR-CY-2026-099	CY-04	accused
FIR-CY-2026-099	CY-05	witness
FIR-CY-2026-099	CY-01	mentioned
\.

-- END OF SYNTHETIC SAMPLE

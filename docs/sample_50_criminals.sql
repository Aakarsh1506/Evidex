--
-- Sample database export: 50 synthetic criminal records.
-- SYNTHETIC DATA — every person, number, address and case below is fictional.
--
-- Upload on the Upload page with source "Database export (SQL dump, SQLite, CSV, JSON)".
-- Rows are read as data and staged for review; no statement here is executed.
--

INSERT INTO crime_types (crime_id, crime_name) VALUES
  (1, 'Theft'),
  (2, 'Financial fraud'),
  (3, 'Burglary'),
  (4, 'Forgery'),
  (5, 'Cheating'),
  (6, 'Extortion');

INSERT INTO locations (location_id, city, state) VALUES
  (1, 'Nandipur', 'Maharashtra'),
  (2, 'Vashi', 'Maharashtra'),
  (3, 'Thane', 'Maharashtra'),
  (4, 'Pune', 'Maharashtra'),
  (5, 'Nashik', 'Maharashtra'),
  (6, 'Bengaluru', 'Karnataka'),
  (7, 'Hyderabad', 'Telangana'),
  (8, 'Surat', 'Gujarat');

INSERT INTO organizations (organization_id, organization_name, city) VALUES
  (1, 'Harbour View Police Station', 'Nandipur'),
  (2, 'Meridian Electronics', 'Nandipur'),
  (3, 'Apex Finserv Private Limited', 'Bengaluru'),
  (4, 'Laxmi Traders', 'Vashi'),
  (5, 'Oceanic Clearing Agency', 'Thane');

INSERT INTO vehicles (vehicle_id, registration, description) VALUES
  (1, 'MH13FR9466', 'Blue scooter, synthetic record.'),
  (2, 'MH42CL9577', 'Black motorcycle, synthetic record.'),
  (3, 'MH38CJ3454', 'White hatchback, synthetic record.'),
  (4, 'MH19HK2011', 'Silver sedan, synthetic record.'),
  (5, 'MH43HK1930', 'White hatchback, synthetic record.'),
  (6, 'MH22EJ2601', 'Blue scooter, synthetic record.'),
  (7, 'MH45AK8262', 'Silver sedan, synthetic record.'),
  (8, 'MH49DN8411', 'Blue scooter, synthetic record.');

INSERT INTO persons (person_id, name, alias, dob, age, city, state, phone, record_status) VALUES
  ('SYN001', 'Ritu Nair', NULL, '1980-02-27', 46, 'Vashi', 'Maharashtra', '9843849730', 'Extracted (unverified)'),
  ('SYN002', 'Deepa Patil', NULL, '1968-09-07', 58, 'Thane', 'Maharashtra', '9710065165', 'Extracted (unverified)'),
  ('SYN003', 'Imran Pawar', NULL, '1979-04-03', 47, 'Pune', 'Maharashtra', '9847920620', 'Extracted (unverified)'),
  ('SYN004', 'Manish Qureshi', NULL, '1969-04-21', 57, 'Nashik', 'Maharashtra', '9868425323', 'Extracted (unverified)'),
  ('SYN005', 'Firoz Qureshi', NULL, '1969-01-08', 57, 'Bengaluru', 'Karnataka', '9712504443', 'Extracted (unverified)'),
  ('SYN006', 'Kunal Nair', NULL, '1987-03-18', 39, 'Hyderabad', 'Telangana', '9731619612', 'Extracted (unverified)'),
  ('SYN007', 'Aarti Ali', 'Aary', '1970-02-19', 56, 'Surat', 'Gujarat', '9853331510', 'Extracted (unverified)'),
  ('SYN008', 'Nandini Menon', NULL, '1982-09-23', 44, 'Nandipur', 'Maharashtra', '9716854787', 'Extracted (unverified)'),
  ('SYN009', 'Aarti Qureshi', NULL, '1992-11-18', 34, 'Vashi', 'Maharashtra', '9814780935', 'Extracted (unverified)'),
  ('SYN010', 'Rajat Kulkarni', NULL, '1976-06-10', 50, 'Thane', 'Maharashtra', '9766686503', 'Extracted (unverified)'),
  ('SYN011', 'Vikram Salvi', NULL, '1990-10-10', 36, 'Pune', 'Maharashtra', '9840981362', 'Extracted (unverified)'),
  ('SYN012', 'Naveen Kulkarni', NULL, '1977-10-03', 49, 'Nashik', 'Maharashtra', '9731693041', 'Extracted (unverified)'),
  ('SYN013', 'Sadia Pawar', NULL, '1995-03-16', 31, 'Bengaluru', 'Karnataka', '9813198790', 'Extracted (unverified)'),
  ('SYN014', 'Kavita Naik', NULL, '2001-06-23', 25, 'Hyderabad', 'Telangana', '9794000295', 'Extracted (unverified)'),
  ('SYN015', 'Shreya Khan', NULL, '1968-02-27', 58, 'Surat', 'Gujarat', '9725124483', 'Extracted (unverified)'),
  ('SYN016', 'Karan Khan', NULL, '2001-12-23', 25, 'Nandipur', 'Maharashtra', '9783109596', 'Extracted (unverified)'),
  ('SYN017', 'Ajay Verma', NULL, '1977-12-13', 49, 'Vashi', 'Maharashtra', '9879490097', 'Extracted (unverified)'),
  ('SYN018', 'Sneha Mehta', NULL, '1976-03-20', 50, 'Thane', 'Maharashtra', '9731432663', 'Extracted (unverified)'),
  ('SYN019', 'Naveen Qureshi', NULL, '1992-03-24', 34, 'Pune', 'Maharashtra', '9766468600', 'Extracted (unverified)'),
  ('SYN020', 'Harish Shah', NULL, '1974-03-15', 52, 'Nashik', 'Maharashtra', '9807815559', 'Extracted (unverified)'),
  ('SYN021', 'Kunal Joshi', NULL, '1997-09-09', 29, 'Bengaluru', 'Karnataka', '9889621923', 'Extracted (unverified)'),
  ('SYN022', 'Zoya Patil', 'Zoyy', '1981-03-03', 45, 'Hyderabad', 'Telangana', '9747303087', 'Extracted (unverified)'),
  ('SYN023', 'Farhan Bhosale', NULL, '1991-08-27', 35, 'Surat', 'Gujarat', '9858141637', 'Extracted (unverified)'),
  ('SYN024', 'Vikram Joshi', NULL, '1987-03-14', 39, 'Nandipur', 'Maharashtra', '9843503168', 'Extracted (unverified)'),
  ('SYN025', 'Gaurav Sethi', NULL, '1969-03-23', 57, 'Vashi', 'Maharashtra', '9838376177', 'Extracted (unverified)'),
  ('SYN026', 'Mohit Bose', NULL, '2002-11-26', 24, 'Thane', 'Maharashtra', '9850128364', 'Extracted (unverified)'),
  ('SYN027', 'Deepa Khan', NULL, '1980-04-03', 46, 'Pune', 'Maharashtra', '9756039440', 'Extracted (unverified)'),
  ('SYN028', 'Rekha Sheikh', NULL, '1998-10-02', 28, 'Nashik', 'Maharashtra', '9727482314', 'Extracted (unverified)'),
  ('SYN029', 'Rohan Verma', NULL, '1996-06-20', 30, 'Bengaluru', 'Karnataka', '9706845343', 'Extracted (unverified)'),
  ('SYN030', 'Priya Menon', 'Priy', '1981-11-09', 45, 'Hyderabad', 'Telangana', '9793251671', 'Extracted (unverified)'),
  ('SYN031', 'Shreya Patil', NULL, '1975-02-28', 51, 'Surat', 'Gujarat', '9831014770', 'Extracted (unverified)'),
  ('SYN032', 'Tarun Khan', NULL, '1975-02-05', 51, 'Nandipur', 'Maharashtra', '9727430779', 'Extracted (unverified)'),
  ('SYN033', 'Vivek Kulkarni', NULL, '1989-12-06', 37, 'Vashi', 'Maharashtra', '9838602492', 'Extracted (unverified)'),
  ('SYN034', 'Sameer Menon', NULL, '1972-03-23', 54, 'Thane', 'Maharashtra', '9845806736', 'Extracted (unverified)'),
  ('SYN035', 'Sameer Kadam', NULL, '1972-11-28', 54, 'Pune', 'Maharashtra', '9724430458', 'Extracted (unverified)'),
  ('SYN036', 'Divya Joshi', NULL, '1972-03-12', 54, 'Nashik', 'Maharashtra', '9759805474', 'Extracted (unverified)'),
  ('SYN037', 'Bhavna Gowda', NULL, '1973-11-08', 53, 'Bengaluru', 'Karnataka', '9864612197', 'Extracted (unverified)'),
  ('SYN038', 'Simran Menon', NULL, '1990-12-26', 36, 'Hyderabad', 'Telangana', '9760864918', 'Extracted (unverified)'),
  ('SYN039', 'Sunita Reddy', NULL, '1974-12-01', 52, 'Surat', 'Gujarat', '9707499301', 'Extracted (unverified)'),
  ('SYN040', 'Lakshmi Menon', NULL, '1983-12-12', 43, 'Nandipur', 'Maharashtra', '9797881200', 'Extracted (unverified)'),
  ('SYN041', 'Imran Bhosale', 'Imry', '1999-08-07', 27, 'Vashi', 'Maharashtra', '9790660714', 'Extracted (unverified)'),
  ('SYN042', 'Rakesh Khan', NULL, '2005-11-12', 21, 'Thane', 'Maharashtra', '9872639727', 'Extracted (unverified)'),
  ('SYN043', 'Imran Naik', NULL, '1998-12-25', 28, 'Pune', 'Maharashtra', '9753504394', 'Extracted (unverified)'),
  ('SYN044', 'Ishita Sheikh', NULL, '1978-02-26', 48, 'Nashik', 'Maharashtra', '9893763351', 'Extracted (unverified)'),
  ('SYN045', 'Harish Iyer', NULL, '1980-12-06', 46, 'Bengaluru', 'Karnataka', '9745635009', 'Extracted (unverified)'),
  ('SYN046', 'Meera Mehta', NULL, '1996-11-05', 30, 'Hyderabad', 'Telangana', '9864167966', 'Extracted (unverified)'),
  ('SYN047', 'Ruchi Patil', 'Rucy', '1996-01-01', 30, 'Surat', 'Gujarat', '9894983477', 'Extracted (unverified)'),
  ('SYN048', 'Ajay Deshmukh', 'Ajay', '1972-07-28', 54, 'Nandipur', 'Maharashtra', '9752292687', 'Extracted (unverified)'),
  ('SYN049', 'Rakesh Mehta', 'Raky', '1989-05-17', 37, 'Vashi', 'Maharashtra', '9764569300', 'Extracted (unverified)'),
  ('SYN050', 'Simran Verma', NULL, '1985-09-14', 41, 'Thane', 'Maharashtra', '9735184823', 'Extracted (unverified)');

INSERT INTO cases (case_id, crime_id, location_id, case_status, case_month) VALUES
  ('FIR-SYN-2026-1001', 2, 2, 'Charge sheet filed', '2026-02-01'),
  ('FIR-SYN-2026-1002', 3, 3, 'Closed', '2026-03-01'),
  ('FIR-SYN-2026-1003', 4, 4, 'Under investigation', '2026-04-01'),
  ('FIR-SYN-2026-1004', 5, 5, 'Charge sheet filed', '2026-05-01'),
  ('FIR-SYN-2026-1005', 6, 6, 'Closed', '2026-06-01'),
  ('FIR-SYN-2026-1006', 1, 7, 'Under investigation', '2026-07-01'),
  ('FIR-SYN-2026-1007', 2, 8, 'Charge sheet filed', '2026-08-01'),
  ('FIR-SYN-2026-1008', 3, 1, 'Closed', '2026-09-01'),
  ('FIR-SYN-2026-1009', 4, 2, 'Under investigation', '2026-10-01'),
  ('FIR-SYN-2026-1010', 5, 3, 'Charge sheet filed', '2026-11-01'),
  ('FIR-SYN-2026-1011', 6, 4, 'Closed', '2026-12-01'),
  ('FIR-SYN-2026-1012', 1, 5, 'Under investigation', '2026-01-01'),
  ('FIR-SYN-2026-1013', 2, 6, 'Charge sheet filed', '2026-02-01'),
  ('FIR-SYN-2026-1014', 3, 7, 'Closed', '2026-03-01'),
  ('FIR-SYN-2026-1015', 4, 8, 'Under investigation', '2026-04-01'),
  ('FIR-SYN-2026-1016', 5, 1, 'Charge sheet filed', '2026-05-01'),
  ('FIR-SYN-2026-1017', 6, 2, 'Closed', '2026-06-01'),
  ('FIR-SYN-2026-1018', 1, 3, 'Under investigation', '2026-07-01');

-- Join table: each row links a person to a case with the role recorded in the source.
COPY case_people (case_id, person_id, role) FROM stdin;
FIR-SYN-2026-1001	SYN001	suspect
FIR-SYN-2026-1001	SYN019	witness
FIR-SYN-2026-1001	SYN037	suspect
FIR-SYN-2026-1002	SYN002	suspect
FIR-SYN-2026-1002	SYN020	complainant
FIR-SYN-2026-1002	SYN038	accused
FIR-SYN-2026-1003	SYN003	accused
FIR-SYN-2026-1003	SYN016	accused
FIR-SYN-2026-1003	SYN021	suspect
FIR-SYN-2026-1003	SYN034	suspect
FIR-SYN-2026-1003	SYN039	witness
FIR-SYN-2026-1004	SYN004	witness
FIR-SYN-2026-1004	SYN022	suspect
FIR-SYN-2026-1004	SYN040	complainant
FIR-SYN-2026-1005	SYN005	complainant
FIR-SYN-2026-1005	SYN023	accused
FIR-SYN-2026-1005	SYN041	suspect
FIR-SYN-2026-1006	SYN001	accused
FIR-SYN-2026-1006	SYN006	suspect
FIR-SYN-2026-1006	SYN019	suspect
FIR-SYN-2026-1006	SYN024	witness
FIR-SYN-2026-1006	SYN037	witness
FIR-SYN-2026-1006	SYN042	suspect
FIR-SYN-2026-1007	SYN007	suspect
FIR-SYN-2026-1007	SYN025	complainant
FIR-SYN-2026-1007	SYN043	accused
FIR-SYN-2026-1008	SYN008	accused
FIR-SYN-2026-1008	SYN026	suspect
FIR-SYN-2026-1008	SYN044	witness
FIR-SYN-2026-1009	SYN004	suspect
FIR-SYN-2026-1009	SYN009	witness
FIR-SYN-2026-1009	SYN022	witness
FIR-SYN-2026-1009	SYN027	suspect
FIR-SYN-2026-1009	SYN040	suspect
FIR-SYN-2026-1009	SYN045	complainant
FIR-SYN-2026-1010	SYN010	complainant
FIR-SYN-2026-1010	SYN028	accused
FIR-SYN-2026-1010	SYN046	suspect
FIR-SYN-2026-1011	SYN011	suspect
FIR-SYN-2026-1011	SYN029	witness
FIR-SYN-2026-1011	SYN047	suspect
FIR-SYN-2026-1012	SYN007	witness
FIR-SYN-2026-1012	SYN012	suspect
FIR-SYN-2026-1012	SYN025	suspect
FIR-SYN-2026-1012	SYN030	complainant
FIR-SYN-2026-1012	SYN043	complainant
FIR-SYN-2026-1012	SYN048	accused
FIR-SYN-2026-1013	SYN013	accused
FIR-SYN-2026-1013	SYN031	suspect
FIR-SYN-2026-1013	SYN049	witness
FIR-SYN-2026-1014	SYN014	witness
FIR-SYN-2026-1014	SYN032	suspect
FIR-SYN-2026-1014	SYN050	complainant
FIR-SYN-2026-1015	SYN010	suspect
FIR-SYN-2026-1015	SYN015	complainant
FIR-SYN-2026-1015	SYN028	complainant
FIR-SYN-2026-1015	SYN033	accused
FIR-SYN-2026-1015	SYN046	accused
FIR-SYN-2026-1016	SYN016	suspect
FIR-SYN-2026-1016	SYN034	witness
FIR-SYN-2026-1017	SYN017	suspect
FIR-SYN-2026-1017	SYN035	complainant
FIR-SYN-2026-1018	SYN013	complainant
FIR-SYN-2026-1018	SYN018	accused
FIR-SYN-2026-1018	SYN031	accused
FIR-SYN-2026-1018	SYN036	suspect
FIR-SYN-2026-1018	SYN049	suspect
\.

-- END OF SYNTHETIC SAMPLE

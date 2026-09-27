"""Read a database export into reviewable records.

An uploaded export is parsed as data only: its statements are never executed, and nothing is
written until an officer confirms the extraction in review, exactly like an FIR upload.
Supported: plain-text PostgreSQL/MySQL dumps (INSERT and COPY), SQLite files, CSV and JSON.
"""

import csv
import io
import json
import re
import sqlite3
import tempfile
from pathlib import Path

from ..errors import APIError
from .extraction import Entity, Extraction, Relationship, validate_extraction

MAX_TABLES = 60
MAX_ROWS_PER_TABLE = 2000
MAX_CELL = 500
MAX_ENTITIES = 200

# A table's kind: its name is matched first, then its columns, in this order.
TABLE_KINDS = (
    ("Person", r"person|criminal|suspect|accused|individual|witness|offender|people",
     {"name", "full_name", "person_name", "criminal_name"}),
    ("Case", r"\bcase|\bfir(?![a-z])|\bfir_|complaint|incident", {"case_id", "fir_no", "fir_number", "case_no"}),
    ("CrimeType", r"crime_type|crimetype|offen[cs]e|crime", {"crime_name", "offence", "offense"}),
    ("Organization", r"organi[sz]ation|company|firm|business|employer", {"organization_name", "company_name"}),
    ("Vehicle", r"vehicle|car|motorcycle|automobile", {"registration", "plate", "vehicle_no"}),
    ("PhoneNumber", r"phone|mobile|contact_number|msisdn", {"phone_number", "msisdn"}),
    ("Location", r"location|place|address|city|area", {"city", "location_name", "address", "place"}),
)
# A join table only carries keys and a role; its rows link records instead of becoming one.
JOIN_COLUMNS = {"role", "relation", "relationship", "type", "created_at", "updated_at", "id"}
NAME_COLUMNS = ("name", "full_name", "person_name", "criminal_name", "organization_name", "company_name",
                "crime_name", "offence", "offense", "location_name", "city", "place", "registration",
                "vehicle_no", "plate", "phone", "mobile", "phone_number", "case_id", "fir_no", "fir_number", "title")
IDENTIFIER_COLUMNS = ("person_id", "criminal_id", "suspect_id", "accused_id", "witness_id",
                      "case_id", "fir_no", "fir_number", "case_no", "registration", "vehicle_no",
                      "plate", "phone", "mobile", "phone_number")
# Only these identify a record; a phone number is an attribute unless the row is a phone.
RECORD_IDENTIFIERS = ("person_id", "criminal_id", "suspect_id", "accused_id", "witness_id",
                      "case_id", "fir_no", "fir_number", "case_no", "registration", "vehicle_no", "plate")
# Source column -> reviewed attribute key (the closed list in extraction.Attribute).
ATTRIBUTES = {
    "alias": "alias", "nickname": "alias", "aka": "alias",
    "dob": "dob", "date_of_birth": "dob", "birth_date": "dob",
    "age": "age", "height_cm": "height_cm", "height": "height_cm",
    "city": "city", "town": "city", "residence_city": "city",
    "state": "state", "province": "state", "region": "state",
    "last_seen": "last_seen", "last_seen_date": "last_seen",
    "case_month": "case_month", "case_date": "case_month",
    "status": "record_status", "record_status": "record_status", "case_status": "case_status",
    "registration": "registration", "phone": "phone", "mobile": "phone", "phone_number": "phone",
    "description": "description", "notes": "description", "remarks": "description",
    "family_known": "family_known",
}
KINDS = ("Person", "Case", "CrimeType", "Location", "Organization", "Vehicle", "PhoneNumber")
PERSON_HINTS = ("person", "suspect", "accused", "criminal", "witness", "offender", "individual")
CASE_HINTS = ("case", "fir", "complaint", "incident")
CRIME_HINTS = ("crime", "offen")
PLACE_HINTS = ("location", "place", "city", "area", "address")
ROLE_PREDICATES = {"suspect": "SUSPECT_IN", "accused": "SUSPECT_IN", "offender": "SUSPECT_IN",
                   "witness": "WITNESS_IN", "complainant": "MENTIONED_IN", "mentioned": "MENTIONED_IN"}
INSERT = re.compile(r"INSERT\s+INTO\s+[`\"]?(?:\w+[`\"]?\.)?[`\"]?(\w+)[`\"]?\s*(\(([^)]*)\))?\s*VALUES\s*", re.I)
COPY = re.compile(
    r"^COPY\s+[`\"]?(?:\w+[`\"]?\.)?[`\"]?(\w+)[`\"]?\s*(?:\(([^)]*)\))?\s*FROM\s+stdin;\s*$", re.I | re.M)
CREATE_TABLE = re.compile(
    r"CREATE\s+(?:UNLOGGED\s+|TEMP(?:ORARY)?\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"[`\"]?(?:\w+[`\"]?\.)?[`\"]?(\w+)[`\"]?\s*\(", re.I)
# Lines inside CREATE TABLE that define a constraint rather than a column.
CONSTRAINT = re.compile(r"^(?:constraint|primary|foreign|unique|check|exclude|key|index)\b", re.I)


def _clean(value):
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    text = " ".join(text.split())
    return text[:MAX_CELL] or None


def _split_values(text, start):
    """Read one "(...)" tuple of SQL literals, honouring quotes; return (values, next index)."""
    values, current, index, quoted = [], "", start + 1, False
    while index < len(text):
        char = text[index]
        if quoted:
            if char == "'":
                if index + 1 < len(text) and text[index + 1] == "'":
                    current += "'"
                    index += 2
                    continue
                quoted = False
            else:
                current += char
        elif char == "'":
            quoted = True
        elif char in ",)":
            item = current.strip()
            values.append(None if item.upper() in ("NULL", "") else item.strip('"`'))
            current = ""
            if char == ")":
                return values, index + 1
        else:
            current += char
        index += 1
    raise APIError("The dump ends inside a row. Export it again.", 422)


def parse_schema(text):
    """Column names per table from CREATE TABLE, for dumps whose INSERTs omit them."""
    schema = {}
    for match in CREATE_TABLE.finditer(text):
        depth, index = 1, match.end()
        while index < len(text) and depth:
            depth += {"(": 1, ")": -1}.get(text[index], 0)
            index += 1
        body, columns, part, nesting = text[match.end():index - 1], [], "", 0
        for char in body + ",":
            if char in "()":
                nesting += 1 if char == "(" else -1
            if char == "," and not nesting:
                definition = part.strip().strip('`"')
                if definition and not CONSTRAINT.match(definition):
                    columns.append(definition.split()[0].strip('`"').lower())
                part = ""
            else:
                part += char
        if columns:
            schema.setdefault(match[1].lower(), columns)
    return schema


def parse_sql(text):
    tables = {}
    schema = parse_schema(text)
    for match in INSERT.finditer(text):
        table = match[1].lower()
        columns = [c.strip().strip('`"') .lower() for c in (match[3] or "").split(",") if c.strip()]
        index = match.end()
        while index < len(text) and text[index] in " \n\t":
            index += 1
        while index < len(text) and text[index] == "(":
            values, index = _split_values(text, index)
            names = (columns or schema.get(table)
                     or [f"column{n + 1}" for n in range(len(values))])
            rows = tables.setdefault(table, [])
            if len(rows) < MAX_ROWS_PER_TABLE:
                rows.append({name: _clean(value) for name, value in zip(names, values)})
            while index < len(text) and text[index] in " \n\t,":
                if text[index] == ",":
                    index += 1
                    while index < len(text) and text[index] in " \n\t":
                        index += 1
                    break
                index += 1
    for match in COPY.finditer(text):
        table = match[1].lower()
        columns = ([c.strip().strip('`"').lower() for c in (match[2] or "").split(",") if c.strip()]
                   or schema.get(table, []))
        block = text[match.end():]
        end = block.find("\n\\.")
        rows = tables.setdefault(table, [])
        for line in block[: end if end >= 0 else len(block)].splitlines():
            if not line.strip() or len(rows) >= MAX_ROWS_PER_TABLE:
                continue
            values = [None if value == "\\N" else value for value in line.split("\t")]
            names = columns or [f"column{n + 1}" for n in range(len(values))]
            rows.append({name: _clean(value) for name, value in zip(names, values)})
    return tables


def parse_sqlite(content):
    with tempfile.TemporaryDirectory(prefix="cna-import-") as directory:
        path = Path(directory) / "export.sqlite"
        path.write_bytes(content)
        # Read-only: the file is opened as data and no statement from it is executed.
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            connection.row_factory = sqlite3.Row
            names = [row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()[:MAX_TABLES]]
            tables = {}
            for name in names:
                rows = connection.execute(f'SELECT * FROM "{name}" LIMIT {MAX_ROWS_PER_TABLE}').fetchall()
                tables[name.lower()] = [{key.lower(): _clean(row[key]) for key in row.keys()} for row in rows]
            return tables


def parse_rows(content, suffix, stem="import"):
    if content[:5] == b"PGDMP":
        raise APIError(
            "This is a custom-format pg_dump. Export plain SQL instead: "
            "pg_dump --format=plain --column-inserts -d yourdb -f export.sql", 422)
    if suffix in (".sqlite", ".db", ".sqlite3"):
        try:
            return parse_sqlite(content)
        except sqlite3.DatabaseError:
            raise APIError("This file could not be read as a SQLite database.", 422) from None
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise APIError("Upload a UTF-8 text dump, a SQLite file, CSV or JSON.", 422) from None
    if suffix == ".csv":
        reader = csv.DictReader(io.StringIO(text))
        return {stem.lower(): [{(key or "").strip().lower(): _clean(value) for key, value in row.items()}
                               for row in list(reader)[:MAX_ROWS_PER_TABLE]]}
    if suffix == ".json":
        try:
            data = json.loads(text)
        except ValueError:
            raise APIError("This JSON export could not be read.", 422) from None
        if isinstance(data, list):
            data = {stem.lower(): data}
        if not isinstance(data, dict):
            raise APIError("Export JSON as a list of rows or an object of tables.", 422)
        return {str(table).lower(): [{str(key).lower(): _clean(value) for key, value in row.items()}
                                     for row in rows[:MAX_ROWS_PER_TABLE] if isinstance(row, dict)]
                for table, rows in list(data.items())[:MAX_TABLES] if isinstance(rows, list)}
    return parse_sql(text)


def table_kind(table, columns):
    for kind, pattern, _ in TABLE_KINDS:
        if re.search(pattern, table):
            return kind
    for kind, _, markers in TABLE_KINDS:
        if markers & columns:
            return kind
    return None


KEY_FAMILIES = (("person", PERSON_HINTS), ("case", CASE_HINTS), ("crime", CRIME_HINTS),
                ("place", PLACE_HINTS), ("organization", ("organi", "company", "firm")),
                ("vehicle", ("vehicle", "registration", "plate")), ("phone", ("phone", "mobile")))


def key_family(column):
    return next((name for name, hints in KEY_FAMILIES if any(hint in column for hint in hints)), None)


def is_join_table(columns):
    """A join table carries only keys and links exactly two kinds ("case_id" + "person_id").

    A record table keeps its own key as well as its foreign keys ("cases" holds case_id,
    crime_id and location_id), so it is not mistaken for one.
    """
    keys = {c for c in columns if c.endswith("_id") or c in IDENTIFIER_COLUMNS}
    if not columns or keys != {c for c in columns if c not in JOIN_COLUMNS} or len(keys) != 2:
        return False
    return len({key_family(column) for column in keys} - {None}) == 2


def row_name(kind, row):
    for column in NAME_COLUMNS:
        if row.get(column):
            return column, row[column]
    if kind == "Case":
        for column, value in row.items():
            if column.endswith("_id") and value:
                return column, value
    return None, None


def render(table, row, names=None, own=None):
    """One source line per row. A foreign key also shows the record it points at, so a
    link's evidence names both endpoints exactly as the review screen requires."""
    parts = []
    for key, value in row.items():
        if not value:
            continue
        target = (names or {}).get((key, str(value)))
        shown = target if target and target not in (value, own) else None
        parts.append(f"{key}={value}" + (f" ({shown})" if shown else ""))
    return f"{table}: " + " | ".join(parts)


def import_database(content, suffix, stem="import"):
    """Return (source text, extraction) for review. Rows become entities, keys become links."""
    tables = parse_rows(content, suffix, stem)
    if not tables:
        raise APIError("No table rows were found in this export.", 422)
    # Without column names (pg_dump --data-only --inserts, with no CREATE TABLE) a row is just
    # positional values, and no column can be read as a name, date of birth or phone number.
    if all(column.startswith("column") for rows in tables.values() for row in rows for column in row):
        raise APIError(
            "This export has no column names, so its values cannot be read as records. Re-export "
            "with column names: pg_dump --column-inserts -d yourdb -f export.sql", 422)
    drafts, by_key, key_names = [], {}, {}
    for table, rows in tables.items():
        columns = {key for row in rows for key in row}
        kind = None if is_join_table(columns) else table_kind(table, columns)
        for row in rows:
            entry = {"table": table, "kind": kind, "row": row, "name": None}
            drafts.append(entry)
            if kind is None:
                continue
            column, name = row_name(kind, row)
            if not name or len(name) > 100:
                continue
            if sum(1 for draft in drafts if draft["name"]) >= MAX_ENTITIES:
                raise APIError(
                    f"This export holds more than {MAX_ENTITIES} records. Import a smaller selection.", 413)
            entry.update(name=name, name_column=column)
            for key_column, value in row.items():
                if value and (key_column == "id" or key_column.endswith("_id") or key_column in IDENTIFIER_COLUMNS):
                    by_key.setdefault((kind, str(value)), entry)
                    key_names.setdefault((key_column, str(value)), name)
            by_key.setdefault((kind, str(name)), entry)
    lines = [render(draft["table"], draft["row"], key_names, draft["name"]) for draft in drafts]
    text = "\n".join(lines)
    entities, relationships = [], []
    for line, draft in zip(lines, drafts):
        if not draft["name"]:
            continue
        row, kind = draft["row"], draft["kind"]
        columns = RECORD_IDENTIFIERS if kind != "PhoneNumber" else IDENTIFIER_COLUMNS
        identifier = next((row[c] for c in columns if row.get(c)), None)
        attributes = [{"key": key, "value": row[column]}
                      for column, key in ATTRIBUTES.items()
                      if row.get(column) and column != draft["name_column"] and row[column] in line]
        draft["entity"] = Entity(
            ref=f"e{len(entities) + 1}", kind=kind, name=draft["name"],
            identifier=identifier if identifier and identifier in line else None,
            attributes=attributes[:20], evidence=line)
        entities.append(draft["entity"])
    for line, draft in zip(lines, drafts):
        row = draft["row"]

        def linked(kind, hints):
            """Follow a foreign key: a column named for that kind first, then an unambiguous one."""
            keys = [c for c in row if row.get(c) and (c.endswith("_id") or c in IDENTIFIER_COLUMNS)]

            def entity_for(column):
                target = by_key.get((kind, str(row[column])))
                return target["entity"] if target and target.get("entity") else None

            for column in keys:
                if any(hint in column for hint in hints) and entity_for(column):
                    return entity_for(column)
            for column in keys:
                # An integer key can exist in two tables; only use it when one kind claims it.
                kinds = {other for other in KINDS if (other, str(row[column])) in by_key}
                if kinds == {kind} and entity_for(column):
                    return entity_for(column)
            return None

        person = linked("Person", PERSON_HINTS)
        case = linked("Case", CASE_HINTS)
        if person and case:
            role = str(row.get("role") or row.get("relation") or row.get("type") or "mentioned").lower()
            predicate = next((value for key, value in ROLE_PREDICATES.items() if key in role), "MENTIONED_IN")
            relationships.append(Relationship(subject=person.ref, predicate=predicate, object=case.ref, evidence=line))
        if case:
            # "crime_id", "offence_id", "place_id": the column name does not matter, the
            # record it resolves to does.
            for kind, predicate, hints in (("CrimeType", "OF_TYPE", CRIME_HINTS),
                                           ("Location", "OCCURRED_AT", PLACE_HINTS)):
                target = linked(kind, hints)
                if target and target.ref != case.ref:
                    relationships.append(Relationship(subject=case.ref, predicate=predicate,
                                                      object=target.ref, evidence=line))
    extraction = Extraction(entities=entities, relationships=relationships[:400])
    # Same grounding rules as every other source: unsupported links are kept for review only.
    return text, validate_extraction(extraction, text, exclude_invalid=True)

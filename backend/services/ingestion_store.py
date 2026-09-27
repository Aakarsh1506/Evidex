"""Commit extracted records and a replayable graph payload in one SQL transaction."""

import re
from datetime import date

from psycopg.types.json import Jsonb

from ..errors import APIError
from .crime_terms import is_explicit_crime_field
from .entity_resolution import find_existing, normalized
from .extraction import RELATION_RULES, stable_id

NODE_KEYS = {
    "Person": "person_id",
    "Case": "case_id",
    "Location": "location_id",
    "CrimeType": "crime_id",
    "Organization": "organization_id",
    "Vehicle": "vehicle_id",
    "PhoneNumber": "phone_id",
}

async def mark_import_owned(tx, kind, canonical):
    await tx.query(
        """INSERT INTO ingestion_owned_entities (kind,canonical_id) VALUES (%s,%s)
           ON CONFLICT DO NOTHING""", (kind, str(canonical)),
    )


def properties_for(entity):
    props = {item.key: item.value for item in entity.attributes}
    if "age" in props:
        raw_age = props.pop("age")
        # Preserve the reviewed wording even when it cannot populate an integer column.
        match = re.fullmatch(
            r"([0-9]{1,3})(?:\s*(?:years?(?:\s+old)?|yrs?\.?|y/o))?",
            raw_age.strip(),
            flags=re.IGNORECASE,
        )
        if match and 0 <= int(match[1]) <= 130:
            props["age"] = int(match[1])
        if not match or "age" not in props or raw_age != str(props["age"]):
            props["age_text"] = raw_age
    for field in ("dob", "last_seen", "case_month"):
        if field in props:
            try:
                props[field] = date.fromisoformat(props[field]).isoformat()
            except ValueError:
                raise APIError(f"AI returned an invalid {field} date.", 502) from None
    for field in ("height_cm",):
        if field in props:
            try:
                props[field] = int(props[field])
                if not 0 <= props[field] <= 300:
                    raise ValueError
            except ValueError:
                raise APIError(f"AI returned an invalid {field} value.", 502) from None
    # Existing relational columns are bounded to 100 characters.
    if any(
        len(str(value)) > 100
        for key, value in props.items()
        if key not in {"description", "age_text"}
    ):
        raise APIError("AI returned a field exceeding the database limit.", 502)
    return props


async def canonical_entity(tx, entity, entity_id, props, person_match=None):
    kind, identifier = entity.kind, entity.identifier
    if person_match:
        rows = await tx.query("SELECT * FROM persons WHERE person_id=%s", (person_match,))
        if kind != "Person" or not rows or normalized(rows[0]["name"]) != normalized(entity.name):
            raise APIError("The reviewed person match is no longer available. No records were saved.", 409)
        return person_match, rows[0]
    existing = await find_existing(tx, entity, props)
    if existing:
        return existing
    if kind in ("Person", "Case", "Organization", "Vehicle"):
        table = {
            "Person": "persons",
            "Case": "cases",
            "Organization": "organizations",
            "Vehicle": "vehicles",
        }[kind]
        key = NODE_KEYS[kind]
        canonical = entity_id
        await mark_import_owned(tx, kind, canonical)
        if kind == "Person":
            await tx.query(
                """INSERT INTO persons (person_id, name, alias, dob, age, height_cm,
                   city, state, last_seen, family_known, record_status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (person_id) DO UPDATE SET
                     alias=COALESCE(persons.alias, EXCLUDED.alias),
                     dob=COALESCE(persons.dob, EXCLUDED.dob),
                     age=COALESCE(persons.age, EXCLUDED.age),
                     height_cm=COALESCE(persons.height_cm, EXCLUDED.height_cm),
                     city=COALESCE(persons.city, EXCLUDED.city),
                     state=COALESCE(persons.state, EXCLUDED.state),
                     last_seen=COALESCE(persons.last_seen, EXCLUDED.last_seen),
                     family_known=COALESCE(persons.family_known, EXCLUDED.family_known)""",
                (
                    canonical,
                    entity.name,
                    props.get("alias"),
                    props.get("dob"),
                    props.get("age"),
                    props.get("height_cm"),
                    props.get("city"),
                    props.get("state"),
                    props.get("last_seen"),
                    props.get("family_known"),
                    props.get("record_status") or "Extracted (unverified)",
                ),
            )
        elif kind == "Case":
            # Role-specific links live in extracted_relationships; no invented primary suspect.
            await tx.query(
                """INSERT INTO cases (case_id, case_month, case_status)
                   VALUES (%s,%s,%s) ON CONFLICT (case_id) DO NOTHING""",
                (canonical, props.get("case_month"), props.get("case_status")),
            )
        elif kind == "Organization":
            await tx.query(
                "INSERT INTO organizations VALUES (%s,%s) ON CONFLICT DO NOTHING",
                (canonical, entity.name),
            )
        else:
            await tx.query(
                "INSERT INTO vehicles VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                (canonical, props.get("registration") or identifier, entity.name),
            )
        rows = await tx.query(f"SELECT * FROM {table} WHERE {key} = %s", (canonical,))
        return canonical, rows[0]
    if kind == "CrimeType":
        rows = await tx.query(
            "SELECT * FROM crime_types WHERE lower(crime_name) = lower(%s)", (entity.name,)
        )
        if not rows:
            # The supplied dump resets this sequence below existing IDs.
            await tx.query("""SELECT setval(pg_get_serial_sequence('crime_types','crime_id'),
                GREATEST(COALESCE((SELECT MAX(crime_id) FROM crime_types),0)+1,
                nextval(pg_get_serial_sequence('crime_types','crime_id'))), false)""")
            rows = await tx.query(
                """INSERT INTO crime_types (crime_name, description) VALUES (%s,%s)
                   ON CONFLICT (crime_name) DO UPDATE SET crime_name=EXCLUDED.crime_name
                   RETURNING *""",
                (entity.name, props.get("description")),
            )
            await mark_import_owned(tx, kind, rows[0]["crime_id"])
        return rows[0]["crime_id"], rows[0]
    if kind == "Location":
        city, state = props.get("city") or entity.name, props.get("state")
        rows = await tx.query(
            "SELECT * FROM locations WHERE lower(city)=lower(%s) AND state IS NOT DISTINCT FROM %s",
            (city, state),
        )
        if not rows:
            rows = await tx.query(
                "INSERT INTO locations (city,state) VALUES (%s,%s) RETURNING *", (city, state)
            )
            await mark_import_owned(tx, kind, rows[0]["location_id"])
        # Geometry is not a Neo4j property; preserve only the mapped source fields.
        return rows[0]["location_id"], {k: v for k, v in rows[0].items() if k != "geom"}
    await mark_import_owned(tx, kind, entity_id)
    return entity_id, {"name": entity.name, "number": identifier or entity.name}


async def persist_extraction(db, document_id, result):
    async with db.transaction() as tx:
        # Serialize imports to avoid duplicate shared lookups across server workers.
        await tx.query("SELECT pg_advisory_xact_lock(724013)")
        rows = await tx.query(
            "SELECT graph_payload, confirmed_at, person_matches FROM officer_documents WHERE document_id=%s FOR UPDATE",
            (document_id,),
        )
        if rows[0]["graph_payload"] is not None:
            return rows[0]["graph_payload"]
        if rows[0]["confirmed_at"] is None:
            raise APIError("Review and confirm the extraction before saving records.", 409)
        person_matches = rows[0].get("person_matches") or {}
        nodes, refs = [], {}
        for entity in result.entities:
            if entity.kind == "CrimeType":
                # Source wording is kept; the saved label is sentence case, so "theft",
                # "BURGLARY" and "Theft" cannot become three differently spelled rows.
                name = entity.name
                name = name.capitalize() if name.isupper() else name[:1].upper() + name[1:]
                entity = entity.model_copy(update={"name": name})
            entity_id = stable_id(document_id, entity.ref)
            props = properties_for(entity)
            canonical, row = await canonical_entity(tx, entity, entity_id, props, person_matches.get(entity.ref))
            # Convert dates and numeric coordinates to graph-compatible scalar values.
            graph_props = {
                k: (v if isinstance(v, (str, int, float, bool)) else str(v))
                for k, v in row.items()
                if v is not None
            }
            graph_props.setdefault("name", entity.name)
            graph_props[NODE_KEYS[entity.kind]] = canonical
            graph_props["source"] = "document_extraction"
            graph_props["review_status"] = "unverified"
            nodes.append({"kind": entity.kind, "id": canonical, "properties": graph_props})
            refs[entity.ref] = {"entity_id": entity_id, "kind": entity.kind, "id": canonical}
            await tx.query(
                """INSERT INTO extracted_entities
                   (entity_id,document_id,kind,canonical_id,name,properties,evidence)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (
                    entity_id,
                    document_id,
                    entity.kind,
                    str(canonical),
                    entity.name,
                    Jsonb({**props, "source_identifier": entity.identifier}),
                    entity.evidence,
                ),
            )
        edges = []
        for relation in result.relationships:
            subject, target = refs[relation.subject], refs[relation.object]
            relation_id = stable_id(
                document_id, relation.subject, relation.predicate, relation.object
            )
            await tx.query(
                """INSERT INTO extracted_relationships
                   (relationship_id,document_id,subject_id,predicate,object_id,evidence)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (
                    relation_id,
                    document_id,
                    subject["entity_id"],
                    relation.predicate,
                    target["entity_id"],
                    relation.evidence,
                ),
            )
            edges.append(
                {
                    "id": relation_id,
                    "subject": subject,
                    "object": target,
                    "predicate": relation.predicate,
                    "evidence": relation.evidence,
                }
            )
            # Populate legacy single-value case columns only for newly imported cases.
            if relation.predicate in ("OCCURRED_AT", "OF_TYPE") and subject["kind"] == "Case":
                column = "location_id" if relation.predicate == "OCCURRED_AT" else "crime_id"
                await tx.query(
                    f"UPDATE cases SET {column}=COALESCE({column},%s) WHERE case_id=%s",
                    (target["id"], subject["id"]),
                )
        # Some local models return the explicit crime field as an entity but omit
        # the OF_TYPE edge. When the FIR has exactly one case and one crime type,
        # preserve that explicit source assertion without guessing across cases.
        cases = [entity for entity in result.entities if entity.kind == "Case"]
        crime_types = [
            entity for entity in result.entities
            if entity.kind == "CrimeType"
            and is_explicit_crime_field(entity.evidence, entity.name)
        ]
        if len(cases) == 1 and len(crime_types) == 1:
            case_ref, crime_ref = refs[cases[0].ref], refs[crime_types[0].ref]
            if not any(
                relation.predicate == "OF_TYPE"
                and relation.subject == cases[0].ref
                for relation in result.relationships
            ):
                await tx.query(
                    "UPDATE cases SET crime_id=COALESCE(crime_id,%s) WHERE case_id=%s",
                    (crime_ref["id"], case_ref["id"]),
                )
        # Use an explicitly connected location (direct links first, then a case).
        # An incident location is a connected place, not proof of a sighting.
        by_ref = {entity.ref: entity for entity in result.entities}
        node_by_id = {(node["kind"], str(node["id"])): node for node in nodes}
        for person_ref, person in refs.items():
            if person["kind"] != "Person":
                continue
            choices = []
            linked_cases = {
                relation.object for relation in result.relationships
                if relation.subject == person_ref
                and relation.predicate in ("MENTIONED_IN", "WITNESS_IN", "SUSPECT_IN")
            }
            for relation in result.relationships:
                if relation.subject == person_ref and relation.predicate in ("SEEN_AT", "RESIDES_IN"):
                    choices.append((0 if relation.predicate == "SEEN_AT" else 1, relation.object))
                elif relation.subject in linked_cases and relation.predicate == "OCCURRED_AT":
                    choices.append((2, relation.object))
            if not choices:
                continue
            location_ref = min(choices)[1]
            location = by_ref[location_ref]
            location_node = node_by_id[("Location", str(refs[location_ref]["id"]))]
            city = location_node["properties"].get("city") or location.name
            state = location_node["properties"].get("state")
            await tx.query(
                "UPDATE persons SET city=%s,state=%s WHERE person_id=%s",
                (city, state, person["id"]),
            )
            node_by_id[("Person", str(person["id"]))]["properties"].update(city=city, state=state)
        payload = {"document_id": document_id, "nodes": nodes, "edges": edges}
        await tx.query(
            """UPDATE officer_documents SET graph_payload=%s,
            processing_status='syncing' WHERE document_id=%s""",
            (Jsonb(payload), document_id),
        )
        return payload


async def sync_graph(graph, payload):
    # Labels and predicates come only from validated allowlists, never raw model strings.
    async def write(tx):
        for node in payload["nodes"]:
            kind, key = node["kind"], NODE_KEYS[node["kind"]]
            result = await tx.run(
                f"MERGE (n:{kind} {{{key}: $id}}) ON CREATE SET n += $props",
                id=node["id"],
                props=node["properties"],
            )
            await result.consume()
            if kind == "Person" and node["properties"].get("city"):
                result = await tx.run(
                    "MATCH (n:Person {person_id:$id}) SET n.city=$city,n.state=$state",
                    id=node["id"], city=node["properties"]["city"],
                    state=node["properties"].get("state"),
                )
                await result.consume()
        for edge in payload["edges"]:
            subject, target = edge["subject"], edge["object"]
            # Validate again at the database boundary, including replays from stored payloads.
            allowed_s, allowed_o = RELATION_RULES[edge["predicate"]]
            if subject["kind"] not in allowed_s or target["kind"] not in allowed_o:
                raise ValueError("Invalid stored relationship")
            result = await tx.run(
                f"MATCH (a:{subject['kind']} {{{NODE_KEYS[subject['kind']]}: $subject}}), "
                f"(b:{target['kind']} {{{NODE_KEYS[target['kind']]}: $object}}) "
                f"MERGE (a)-[r:{edge['predicate']} {{extraction_id: $id}}]->(b) "
                "SET r.source='document_extraction', r.document_id=$document, "
                "r.evidence=$evidence, r.review_status='unverified'",
                subject=subject["id"],
                object=target["id"],
                id=edge["id"],
                document=payload["document_id"],
                evidence=edge["evidence"],
            )
            await result.consume()

    async with graph.driver.session() as session:
        for kind, key in NODE_KEYS.items():
            result = await session.run(
                f"CREATE CONSTRAINT ingestion_{key}_unique IF NOT EXISTS "
                f"FOR (n:{kind}) REQUIRE n.{key} IS UNIQUE"
            )
            await result.consume()
        await session.execute_write(write)

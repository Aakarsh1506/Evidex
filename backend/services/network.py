NETWORK_PATH_LIMIT = 1000


def network_query(root="(root:Person {person_id: $id})"):
    # Explore four hops, allowing crime types only at the end of a path.
    return f"""
  MATCH path = {root}-[*0..4]-(connected)
  WHERE none(node IN nodes(path)[0..-1] WHERE node:CrimeType)
  RETURN path
  ORDER BY length(path), elementId(connected)
  LIMIT {NETWORK_PATH_LIMIT + 1}
"""


NETWORK_QUERY = network_query()
CASE_NETWORK_QUERY = network_query("(root:Case {case_id: $id})")


async def fetch_case_network(case_id, run_cypher):
    return await run_network(CASE_NETWORK_QUERY, case_id, run_cypher)


async def fetch_network(person_id, run_cypher):
    return await run_network(NETWORK_QUERY, person_id, run_cypher)


async def run_network(query, root_id, run_cypher):
    # Request one extra path to detect when the displayed network is truncated.
    records = await run_cypher(query, {"id": root_id})
    if not records:
        return None
    return {
        **serialize_network(records[:NETWORK_PATH_LIMIT]),
        "truncated": len(records) > NETWORK_PATH_LIMIT,
        "pathLimit": NETWORK_PATH_LIMIT,
    }


def serialize_network(records):
    # Merge overlapping paths by graph ID, keeping each node's shortest depth.
    nodes, edges = {}, {}
    for record in records:
        path = record["path"]
        # Python's Path.nodes follows traversal order, even for incoming edges.
        for depth, node in enumerate(path.nodes):
            if node.element_id in nodes:
                nodes[node.element_id]["depth"] = min(nodes[node.element_id]["depth"], depth)
                continue
            kind = next(
                (
                    label
                    for label in (
                        "Person",
                        "Case",
                        "Location",
                        "CrimeType",
                        "Vehicle",
                        "Organization",
                        "PhoneNumber",
                    )
                    if label in node.labels
                ),
                next(iter(sorted(node.labels)), "Record"),
            )
            name = next(
                (
                    node.get(key)
                    for key in (
                        "name",
                        "city",
                        "crime_name",
                        "registration",
                        "case_id",
                        "person_id",
                    )
                    if node.get(key)
                ),
                kind,
            )
            subtitle = f"“{node['alias']}”" if node.get("alias") else node.get("person_id") or ""
            nodes[node.element_id] = {
                "id": node.element_id,
                "kind": kind,
                "depth": depth,
                "label": name,
                "displayLabel": f"{name}\n{subtitle}" if node.get("name") else name,
                "personId": str(node["person_id"]) if node.get("person_id") is not None else None,
                "caseId": str(node["case_id"]) if node.get("case_id") is not None else None,
                "alias": node.get("alias") or None,
                "city": node.get("city") or None,
                "provenance": node.get("source") or None,
            }
        for relationship in path.relationships:
            # Preserve stored edge direction even when a path traverses it backwards.
            edges[relationship.element_id] = {
                "id": relationship.element_id,
                "source": relationship.start_node.element_id,
                "target": relationship.end_node.element_id,
                "label": relationship.type.replace("_", " "),
                "provenance": relationship.get("source") or None,
                "reason": relationship.get("reason") or None,
                **{
                    output: relationship.get(prop)
                    for output, prop in (
                        ("evidence", "evidence"),
                        ("documentId", "document_id"),
                        ("reviewStatus", "review_status"),
                    )
                    if relationship.get(prop) is not None
                },
            }
    return {"nodes": list(nodes.values()), "edges": list(edges.values())}

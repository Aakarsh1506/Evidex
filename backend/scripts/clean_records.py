"""Tidy inconsistent spellings in the shared database.

Shows what it would change and exits; pass --apply to write.
  backend/.venv/bin/python -m backend.scripts.clean_records
  backend/.venv/bin/python -m backend.scripts.clean_records --apply

- Crime types become sentence case ("theft", "BURGLARY" -> "Theft", "Burglary"), matching what
  new imports now save. Rows that would collide with an existing spelling are merged, and the
  cases pointing at them are repointed first.
- Duplicate location rows for the same city and state are reported; merging them is left to an
  officer because a case's location is evidence.
"""

import argparse
import asyncio

from backend.config import Settings
from backend.db import Database


def sentence_case(name):
    name = " ".join(name.split())
    return name.capitalize() if name.isupper() else name[:1].upper() + name[1:]


async def clean(apply):
    db = Database(Settings.from_env())
    await db.open()
    try:
        rows = await db.query("SELECT crime_id, crime_name FROM crime_types ORDER BY crime_id")
        canonical, renames, merges = {}, [], []
        for row in rows:
            wanted = sentence_case(row["crime_name"])
            keeper = canonical.get(wanted.casefold())
            if keeper is None:
                canonical[wanted.casefold()] = row["crime_id"]
                if wanted != row["crime_name"]:
                    renames.append((row["crime_id"], row["crime_name"], wanted))
            else:
                merges.append((row["crime_id"], row["crime_name"], keeper, wanted))
        for crime_id, old, new in renames:
            print(f"rename  crime {crime_id}: {old!r} -> {new!r}")
        for crime_id, old, keeper, new in merges:
            print(f"merge   crime {crime_id}: {old!r} -> crime {keeper} ({new!r})")
        duplicates = await db.query(
            """SELECT lower(btrim(city)) AS city, state, count(*)::int AS rows,
                      array_agg(location_id ORDER BY location_id) AS ids
               FROM locations GROUP BY 1, 2 HAVING count(*) > 1""")
        for row in duplicates:
            print(f"review  duplicate locations {row['ids']} for {row['city']!r}, state {row['state']!r}")
        if not (renames or merges):
            print("Crime type spellings are already consistent.")
        if not apply:
            print("\nDry run. Re-run with --apply to write these changes.")
            return
        async with db.transaction() as tx:
            for crime_id, _old, keeper, _new in merges:
                await tx.query("UPDATE cases SET crime_id=%s WHERE crime_id=%s", (keeper, crime_id))
                await tx.query("UPDATE extracted_entities SET canonical_id=%s WHERE kind='CrimeType' AND canonical_id=%s",
                               (str(keeper), str(crime_id)))
                await tx.query("DELETE FROM crime_types WHERE crime_id=%s", (crime_id,))
            for crime_id, _old, new in renames:
                await tx.query("UPDATE crime_types SET crime_name=%s WHERE crime_id=%s", (new, crime_id))
                await tx.query("UPDATE extracted_entities SET name=%s WHERE kind='CrimeType' AND canonical_id=%s",
                               (new, str(crime_id)))
        print(f"\nApplied: {len(renames)} renamed, {len(merges)} merged.")
        print("Re-sync affected documents if the Neo4j graph should show the new spelling.")
    finally:
        await db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the changes shown by a dry run")
    asyncio.run(clean(parser.parse_args().apply))


if __name__ == "__main__":
    main()

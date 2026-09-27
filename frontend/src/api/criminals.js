// Person-level activity for a case participant. People are no longer browsed on their
// own — the case file is the entry point — so only the activity lookup remains here.

const BASE = "/api/criminals";

export async function fetchCriminalActivity(id, { signal } = {}) {
  const res = await fetch(`${BASE}/${encodeURIComponent(id)}/activity`, { signal });
  if (!res.ok) throw new Error("Failed to load activity timeline");
  return res.json();
}

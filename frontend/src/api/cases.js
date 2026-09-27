// Cases are the primary record. Talks to backend/routes/cases.py.

const BASE = "/api/cases";

export async function fetchCases({ q = "", tags = [] } = {}) {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (tags.length) params.set("tags", tags.join(","));
  const qs = params.toString();
  const res = await fetch(qs ? `${BASE}?${qs}` : BASE);
  if (!res.ok) throw new Error("Failed to load cases");
  return res.json();
}

// Every case on file — used by the full register. fetchCases() returns [] with no query.
export async function fetchAllCases() {
  const res = await fetch(`${BASE}?all=true`);
  if (!res.ok) throw new Error("Failed to load cases");
  return res.json();
}

// The whole case file: fields, people with their roles, source documents, summary.
export async function fetchCaseById(id) {
  const res = await fetch(`${BASE}/${encodeURIComponent(id)}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error("Failed to load case");
  return res.json();
}

export async function fetchCaseNetwork(id, { signal } = {}) {
  const res = await fetch(`${BASE}/${encodeURIComponent(id)}/network`, { signal });
  if (res.status === 404) throw new Error("No network is recorded for this case");
  if (!res.ok) throw new Error("Failed to load case network");
  return res.json();
}

export async function generateCaseSummary(id, language = "en", { signal } = {}) {
  const res = await fetch(`${BASE}/${encodeURIComponent(id)}/summary`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ language }),
    signal,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Failed to generate the case summary");
  return data;
}

// Case categories (crime types), used as the case filter tags.
export async function fetchCrimeTypes() {
  const res = await fetch("/api/crime-types");
  if (!res.ok) throw new Error("Failed to load case categories");
  return res.json();
}

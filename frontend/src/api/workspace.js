// Per-officer "currently working on" state, backed by /api/workspace.
// Keyed by case: the cookie-authenticated backend scopes pin/list to the logged-in officer.

const BASE = "/api/workspace";

export async function fetchWorkspace() {
  const res = await fetch(BASE);
  if (!res.ok) throw new Error("Failed to load workspace");
  return res.json(); // { pinnedId, workingList: [{id, reference, title, status, crimeTags}] }
}

export async function pinCase(caseId) {
  const res = await fetch(`${BASE}/pin`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ caseId }),
  });
  if (!res.ok) throw new Error("Failed to pin case");
  return res.json();
}

export async function unpinCase() {
  const res = await fetch(`${BASE}/pin`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to unpin case");
  return res.json();
}

export async function addToWorkingList(caseId) {
  const res = await fetch(`${BASE}/list`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ caseId }),
  });
  if (!res.ok) throw new Error("Failed to add to list");
  return res.json();
}

export async function removeFromWorkingList(caseId) {
  const res = await fetch(`${BASE}/list/${encodeURIComponent(caseId)}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to remove from list");
  return res.json();
}

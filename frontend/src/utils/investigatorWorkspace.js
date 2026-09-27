// The workspace survives navigation and reloads within a browser session (per tab),
// and is cleared on logout. Networks are re-fetched; only the cases and chat are stored.
// The key carries a version: a workspace saved with person ids cannot be replayed
// against the case endpoints, so an older entry is ignored rather than re-fetched.
export const WORKSPACE_KEY = "cna.investigator.workspace.cases";

export function readWorkspace() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(WORKSPACE_KEY) || "{}");
    return {
      records: Array.isArray(saved.records) ? saved.records.filter((record) => record?.id) : [],
      messages: Array.isArray(saved.messages) ? saved.messages.filter((message) => message?.text) : [],
    };
  } catch {
    return { records: [], messages: [] };
  }
}

export function saveWorkspace(records, messages) {
  try {
    sessionStorage.setItem(WORKSPACE_KEY, JSON.stringify({ records, messages: messages.slice(-20) }));
  } catch {
    // A full or unavailable session store only costs persistence, never the workspace itself.
  }
}

export function clearWorkspace() {
  try {
    sessionStorage.removeItem(WORKSPACE_KEY);
  } catch {
    // Nothing to clear when the session store is unavailable.
  }
}

const normalize = (value) => String(value || "").normalize("NFKC").toLocaleLowerCase().trim();

function distance(a, b) {
  let row = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 0; i < a.length; i++) {
    const next = [i + 1];
    for (let j = 0; j < b.length; j++) {
      next[j + 1] = Math.min(next[j] + 1, row[j + 1] + 1, row[j] + (a[i] === b[j] ? 0 : 1));
    }
    row = next;
  }
  return row[b.length];
}

// Fuzzy search over any record kind; the caller names which fields to match.
// The first field is also the tie-break label.
export function searchRecords(records, query, fields = ["name", "id"]) {
  const words = normalize(query).split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  const label = (record) => String(record[fields[0]] ?? record.id);
  return records.map((record) => {
    const haystack = fields.map((key) => normalize(record[key]));
    const tokens = haystack.flatMap((field) => [field, ...field.split(/\s+/)]);
    const score = words.reduce((total, word) => {
      const best = Math.min(...tokens.map((token) => {
        if (token === word) return 0;
        if (token.startsWith(word)) return .1;
        if (token.includes(word)) return .2;
        const edits = distance(word, token);
        return word.length >= 3 && edits <= (word.length > 5 ? 2 : 1) ? .4 + edits / word.length : Infinity;
      }));
      return total + best;
    }, 0);
    return { record, score };
  }).filter(({ score }) => Number.isFinite(score))
    .sort((a, b) => a.score - b.score || label(a.record).localeCompare(label(b.record)))
    .slice(0, 8).map(({ record }) => record);
}

export function mergeNetworks(entries) {
  const nodes = new Map();
  const edges = new Map();
  for (const { record, network } of entries) {
    for (const node of network.nodes) {
      const previous = nodes.get(node.id);
      if (!previous || node.depth < previous.depth) nodes.set(node.id, { ...node, originRecordId: record.id });
    }
    for (const edge of network.edges) {
      if (!edges.has(edge.id)) edges.set(edge.id, { ...edge, originRecordId: record.id });
    }
  }
  return {
    nodes: [...nodes.values()], edges: [...edges.values()],
    truncated: entries.some(({ network }) => network.truncated),
    pathLimit: entries.reduce((sum, { network }) => sum + (network.pathLimit || 0), 0),
  };
}

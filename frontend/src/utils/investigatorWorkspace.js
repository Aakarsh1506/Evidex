// The workspace survives navigation and reloads within a browser session (per tab),
// and is cleared on logout. Networks are re-fetched; only the people and chat are stored.
export const WORKSPACE_KEY = "cna.investigator.workspace";

export function readWorkspace() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(WORKSPACE_KEY) || "{}");
    return {
      people: Array.isArray(saved.people) ? saved.people.filter((person) => person?.id) : [],
      messages: Array.isArray(saved.messages) ? saved.messages.filter((message) => message?.text) : [],
    };
  } catch {
    return { people: [], messages: [] };
  }
}

export function saveWorkspace(people, messages) {
  try {
    sessionStorage.setItem(WORKSPACE_KEY, JSON.stringify({ people, messages: messages.slice(-20) }));
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

export function searchPeople(people, query) {
  const words = normalize(query).split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  return people.map((person) => {
    const fields = [person.name, person.id].map(normalize);
    const tokens = fields.flatMap((field) => [field, ...field.split(/\s+/)]);
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
    return { person, score };
  }).filter(({ score }) => Number.isFinite(score))
    .sort((a, b) => a.score - b.score || a.person.name.localeCompare(b.person.name))
    .slice(0, 8).map(({ person }) => person);
}

export function mergeNetworks(entries) {
  const nodes = new Map();
  const edges = new Map();
  for (const { person, network } of entries) {
    for (const node of network.nodes) {
      const previous = nodes.get(node.id);
      if (!previous || node.depth < previous.depth) nodes.set(node.id, { ...node, originPersonId: person.id });
    }
    for (const edge of network.edges) {
      if (!edges.has(edge.id)) edges.set(edge.id, { ...edge, originPersonId: person.id });
    }
  }
  return {
    nodes: [...nodes.values()], edges: [...edges.values()],
    truncated: entries.some(({ network }) => network.truncated),
    pathLimit: entries.reduce((sum, { network }) => sum + (network.pathLimit || 0), 0),
  };
}

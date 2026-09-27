// A database import stores one line per source row: "table: column=value | column=value".
// Parsing them back into tables lets review show the import as the tables it came from.
export function parseImportedRows(text) {
  const tables = new Map();
  for (const line of (text || "").split("\n")) {
    const separator = line.indexOf(": ");
    if (separator < 0) continue;
    const table = line.slice(0, separator).trim();
    const row = {};
    for (const field of line.slice(separator + 2).split(" | ")) {
      const equals = field.indexOf("=");
      if (equals > 0) row[field.slice(0, equals).trim()] = field.slice(equals + 1).trim();
    }
    if (!table || !Object.keys(row).length) continue;
    if (!tables.has(table)) tables.set(table, []);
    tables.get(table).push(row);
  }
  // Column order follows first appearance, so a table reads like its export.
  return [...tables].map(([name, rows]) => ({
    name,
    columns: [...new Set(rows.flatMap((row) => Object.keys(row)))],
    rows,
  }));
}

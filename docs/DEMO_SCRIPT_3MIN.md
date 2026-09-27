# Criminal Network Analysis — 3-minute demo script

One continuous walkthrough, written the way you'd say it. Plain text is spoken; **[SHOW]** is what
you click. About 660 words — roughly 3:45 at a brisk pace. Timings are cumulative. The appendix answers
"which part is the AI?" in more detail than the demo has time for.

**Before you start:** logged in as an officer, dashboard open, one person pinned, two or three FIRs
and `docs/sample_database_export.sql` ready to upload, and a person already on file whose name also
appears in those FIRs.

---

## 0:00 — Starting on the dashboard (30 s)

**[SHOW]** Dashboard.

So this is where an officer lands: their pinned person, working list, records on file, the crime
tags coming up most often, and the cities involved.

**[SHOW]** Search page: type a name, filter by a crime tag, add someone to the working list.

Search matches names, aliases and crime types, and anyone can go straight into my working list.

## 0:30 — Let's open a profile (35 s)

**[SHOW]** Open a profile: dossier fields, case history. Toggle Map. Pin.

Opening a record gives me the dossier — identity details, case history with the role in each case,
and connected locations on a map.

**[SHOW]** Switch to the graph: zoom, Fit, click a node, then a link.

Now the network. It follows connections four steps out, colour-coded by type, and clicking a person
dims everything unrelated. Clicking a link is the important bit: the evidence behind it, the
document it's in, and whether it's verified. Records sharing several relationships draw as one line.

**[SHOW]** AI insight button.

Anything here can be explained by the AI, from what's on file.

## 1:05 — Now let's add some documents (60 s)

**[SHOW]** Upload page: select three FIRs at once. Then pick Database export and upload the sample
`.sql`.

I can upload a whole batch — FIRs, call records, financial records, surveillance, social media,
criminal history, intelligence. Or import a unit's existing database: a PostgreSQL dump, SQLite, CSV
or JSON. That dump is only ever read as data; nothing in it is executed. This feature is added to improve integration with existing databases like ICCNS and ICJNS

**[SHOW]** Progress bar; point out Stop, Process again, Retry saving, Remove, Open original.

Each reports progress, and I can stop, retry or remove it, or open the original. Documents are also
split into passages and indexed on the way through — both a keyword index and embeddings — which is
the RAG index the AI searches later.

While these run, here's what's happening underneath — and deliberately to improve performance, not all of it is AI. PDFs
are read directly, scans go through OCR here. FIR numbers, mobiles and registrations come from plain
regex, names from a fine-tuned spaCy model.

Relevant evidence is extracted and sent to our local trained AI model while extracts Relationships between the entities.

## 2:05 — So let's review what came out (35 s)

**[SHOW]** Review screen: evidence quotes, keep/reject, the excluded list, confirm.

Nothing reaches the database until we confirm here. Every record shows the exact text behind it.

**[SHOW]** Identity dialog, then the list turning to "Relations saved".

This name already exists, so rather than guess, it shows me that record's age, place and FIRs, and I
decide. Only a matching phone, date of birth or alias merges on its own. On confirmation the records
go into PostgreSQL and the relationships into Neo4j.

## 2:40 — And finally, the investigator workspace (45 s)

**[SHOW]** "Add to Investigator Analysis"; add a second person; ask without selecting anything; then
select a link and ask a follow-up.

This is where it comes together. I pull several people's networks into one view and ask — with a
record selected, or about the whole network. The patterns are computed by the backend, not left to
the model: who recurs across cases, which case ties several people together, a residence that's also
an incident location. The model writes the reading of them, so answers name records, separate leads
from proof, and end with specific checks.

**[SHOW]** An answer citing a document passage.

Answers aren't limited to the graph either. This is the RAG layer: every question runs keyword
search and embedding search over the indexed passages, fuses the two rankings, and keeps the best
few — scoped to this officer's own files, and to this person. So the AI can quote a line from the
FIR that never became a link. And the workspace stays as I left it.

**[SHOW]** Language toggle to Hindi; `/admin`.

Same thing in Hindi, admins manage officer accounts here — and all of it runs on the officer's own
machine.

## 3:25 — Where the AI actually sits (20 s)

**[SHOW]** Back to the graph, or the last answer on screen.

So, which part is the AI? Four: the spaCy model that spots names, the language model reading
narrative into relationships, that same model writing insights and answers, and the RAG layer —
keyword plus embedding search — that feeds it the right passages. All of it local.

Everything else is deterministic: the regex identifiers, layout rules, cleaning, validation,
patterns, identity matching. The model is used only where the document is genuinely free text, it's
constrained and checked, and an officer confirms before anything is saved — which is why this works
with a small model on a laptop.

---

## Appendix — "So which part is the AI?" (for questions)

| Stage | What runs | AI? |
|---|---|---|
| Scanned pages to text | Tesseract OCR | Trained model |
| Names of people, organisations, places | Fine-tuned spaCy NER (or `en_core_web_lg`) | Trained model, not an LLM |
| FIR numbers, phones, vehicle registrations | Regular expressions | No |
| Entity cleaning: dates, amounts, "Age", BNS, courts; suffix typing | Rules (`entity_spans.py`) | No |
| Relationships from FIR layout and fixed phrases | Rules (`structural_relations.py`) | No |
| Relationships from narrative sentences | LLM — qwen3 via Ollama, or Groq | Yes; grammar-constrained, line-number evidence |
| Validation of every model suggestion | Rules (`extraction.validate_extraction`) | No |
| AI insight on a selected record | LLM | Yes |
| Investigator chat answer wording | LLM | Yes |
| Patterns quoted inside that answer | Computed from the graph (`insight.network_analysis`) | No |
| Document indexing (RAG) | Text split into ~1,600-character passages with overlap, stored with a PostgreSQL full-text index and `embeddinggemma` vectors | Embedding model |
| Passage retrieval (RAG) | Keyword and vector search run together, fused by reciprocal rank, scoped to the officer's documents and the selected person, near-duplicates dropped; falls back to keyword-only if embeddings are unavailable | Embedding model + SQL |
| Identity matching, database import, graph queries | Rules and SQL/Cypher | No |

Short version: the AI reads free text and writes prose. Everything structural — and every check on
what the AI produced — is deterministic code.

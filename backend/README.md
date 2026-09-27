# FastAPI backend

`backend` is the Python/FastAPI version of the API. It exposes the same `/api/...` routes as the Express backend and uses the existing PostgreSQL schema, Neo4j graph, JWT cookie, and PDF filenames. The frontend can use it through its existing proxy on port 5050.

## Run

Run these commands from the repository root with Python 3.11 or newer (verified on Python 3.13):

```bash
python3 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install -r backend/requirements.txt
```

Keep your existing `backend/.env`. If it does not exist, copy `backend/.env.example` to `backend/.env` and configure the PostgreSQL, Neo4j, and JWT settings. Environment variables override values in that file. The configuration path is relative to `backend`, independent of the launch directory.

Stop any other backend using port 5050, then start FastAPI from the repository root:

```bash
python -m backend.server
```

With the virtual environment activated, `npm run server:fastapi` does the same thing.

For automatic reload during development:

```bash
python -m uvicorn backend.server:app --reload --port 5050
```

Start the frontend in another terminal with `npm run dev`. The API health endpoint is `http://localhost:5050/api/health`; interactive API documentation is at `http://localhost:5050/docs`.

`python -m backend.server` reads `PORT` from the environment/configuration (default 5050). If you use the Uvicorn CLI, pass its port explicitly. Production HTTPS cookies retain the existing `NODE_ENV=production` switch. Keep the same `JWT_SECRET` and `COOKIE_NAME` when switching servers to preserve signed-in sessions.

## Database and files

The API reads the existing `persons`, `cases`, `locations`, and `crime_types` tables. Startup creates the officers, workspace, and document metadata tables if missing; it does not seed or replace criminal records. Reference SQL is in `sql/`. Database connections and the HTTP client are opened and closed with the app's [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/).

If database initialization is unavailable, the server logs the failure and starts in the same degraded mode as the original backend. `/api/health` is a liveness check, not a database-readiness check. Database-dependent requests return the existing error responses.

Uploaded file contents are stored in PostgreSQL (`officer_document_files`), so every backend connected to the same database can process and open any document. Files uploaded before this change may still be in `backend/uploads/`; they are copied into the database the first time they are opened or processed, or all at once with `python -m backend.scripts.migrate_uploads`. Uploads use multipart field `file` plus a source category and enforce the 20 MB limit. See the extraction section below for the supported formats and processing flow. File listing, download, and deletion remain scoped to the officer ID from the signed cookie.

## API compatibility

| Area | Endpoints |
| --- | --- |
| Authentication | `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` |
| Criminal records | `GET /api/criminals`, `GET /api/criminals/{id}` |
| Graph and AI | `GET /api/criminals/{id}/network`, `POST /api/criminals/{id}/explain` |
| Dashboard | `GET /api/crime-types`, `GET /api/stats` |
| Workspace | `GET /api/workspace`, `PUT/DELETE /api/workspace/pin`, `POST /api/workspace/list`, `DELETE /api/workspace/list/{personId}` |
| Officer administration | `GET/POST /api/officers`, `PATCH /api/officers/{id}/deactivate` |
| Documents | `GET/POST /api/documents`, `GET /api/documents/{id}/file`, `DELETE /api/documents/{id}` |
| Health | `GET /api/health` |

The migration preserves camelCase payload fields and `{ "error": "..." }` failures. Invalid request bodies return 400 rather than FastAPI's default 422. Existing bcrypt password hashes and HS256 JWT cookies remain valid. The admin-only officer API always creates the `officer` role, regardless of client-supplied role fields.

The network query retains the four-hop limit and 1,000-path cap. Crime-type nodes are endpoints, so traversal cannot expand through them into other cases. Native Neo4j node and relationship IDs and original edge directions are retained.

Groq remains optional, configured with `GROQ_API_KEY` and `GROQ_MODEL`. The provider timeout is 30 seconds and at most three explanations run concurrently per server worker. Provider errors are sanitized, and source record limits and prompts are preserved.

## Add an officer

From the repository root, with the virtual environment active:

```bash
python -m backend.scripts.add_officer --username jdoe --name "Jane Doe" --org "Delhi Police" --dob 1990-05-14
```

The script prompts for a password. `--password` and `--role` are also supported for compatibility with the old CLI; the default role is `officer`.

## Verify

```bash
python -m pip install -r backend/requirements-dev.txt
python -m pytest backend/tests -q
python -m ruff check backend
python -m ruff format --check backend
```

Tests use temporary upload directories and isolated database/provider fixtures. They cover route parity against the Express snapshot, existing JWT/bcrypt compatibility, permissions, profiles, workspace isolation, native Neo4j paths, uploads, and AI failures/concurrency. They do not require database credentials or make Groq requests. The dependency versions in `requirements.txt` and `requirements-dev.txt` are pinned to the tested environment; the `.in` files record the supported dependency ranges.

## Document extraction and database import

The Upload page accepts seven source categories: FIR/police reports, CDRs, financial records,
surveillance reports, social media intelligence, criminal history, and intelligence reports.
Supported file formats are PDF, PNG/JPEG/TIFF, UTF-8 TXT/CSV/JSON, and DOCX. CSV and JSON are
read as text for extraction; this is not a raw SQL importer or a transaction anomaly detector.

A **Database export** source type imports an existing database instead of a document. Plain-text
PostgreSQL/MySQL dumps (`INSERT` and `COPY`), SQLite files, CSV and JSON exports are read as data by
`services/database_import.py`: statements in the file are never executed against this database.
Rows become entity candidates (people, cases, locations, crime types, organizations, vehicles,
phones), foreign keys and join tables such as `case_people` become relationships, and each record
cites the row it came from. The result is staged for the same officer review as any other upload;
nothing is saved until it is confirmed. Custom-format `pg_dump` files are rejected with instructions
to export plain SQL (`pg_dump --format=plain --column-inserts`). Limits: 2,000 rows per table,
60 tables and 200 records per import. A ready-made example to try is `docs/sample_database_export.sql`
(synthetic records: 5 people, 2 cases, places, an organization and a vehicle).

Scanned PDFs and images use local Tesseract OCR. Digital PDFs and Word/text files use their
embedded text. The default hybrid mode extracts entity candidates across the document with
spaCy and regex. Candidates are retained with source context and sent to the AI only for
relationship cue sentences; there is no separate AI entity-checking stage. Names and types
come from the local extractor and remain visible in the review screen.
Crime candidates also come from literal offence phrases in narratives (for example,
“suspected financial fraud”), not just `Crime type:` fields. Vocabulary lives in
`backend/services/crime_terms.py`. The source wording and qualifiers are retained as
evidence; a crime mention alone does not assign that crime to a case or person.
Next, relationship cues such as “contacted”, “mentioned”, “witness”, “resides”, and “seen”
select complete source sentences for relationship extraction. A cue is not proof of a link:
the AI checks the sentence, negations, endpoint types, and source evidence before returning
relationships. Preceding sentences are included for pronoun context.
Set `EXTRACTION_MODE=groq` to use the original full AI entity and relationship extraction.
Groq cites numbered source-line ranges; the server copies the original text into each evidence field. The server validates names, source quotes, references, allowed predicates, and directions.
This checks structural validity and quoted evidence; it does not independently verify whether
an allegation or model interpretation is true. Results are staged for review. Entity records and graph relationships are saved only after
the uploading officer confirms the exact draft, and remain unverified source assertions. Witnesses and mentioned people retain their specific case roles.

Install Python dependencies with `python -m pip install -r backend/requirements.txt`.
Install the Tesseract executable separately (`brew install tesseract` on macOS, or your
platform's Tesseract package). English OCR is the default. For other languages, install their
Tesseract trained data and set `OCR_LANGUAGE` (for example `eng+hin`).

Configure `GROQ_API_KEY` in `backend/.env`. Optional settings:

```dotenv
GROQ_EXTRACTION_MODEL=openai/gpt-oss-20b
EXTRACTION_MODE=hybrid
SPACY_MODEL=en_core_web_sm
OCR_LANGUAGE=eng
```

The Python requirements include spaCy and its English `en_core_web_sm` model. After pulling
this change, reinstall `backend/requirements.txt` in your backend virtual environment and
restart FastAPI. Model loading happens locally on the first extraction and is cached.
Missing model installations produce a setup error; they do not silently switch to Groq.

Hybrid extraction uses spaCy for people, organizations and places, plus regex for Indian
mobile numbers, vehicle registrations and FIR IDs. Explicit `Name:`, `Suspect:`, `Witness:`,
`Company:`, `Crime type:` and similar fields supplement NER. Consecutive labeled fields
for age, phone/mobile, alias, ISO DOB, city and state immediately after a named-person
record become attributes. Unlabeled or distant attributes are not inferred. Phone numbers
also remain separate candidates; the app does not infer ownership from proximity.
When saving, exact age wording such as `34 years` becomes numeric age `34`. Ranges,
approximations, unknown values and out-of-range ages remain source text (`age_text` in
the extracted entity properties), with no guessed numeric age. The reviewed attribute
and original evidence are retained.
Explicit `Address:`, `Location:`, `Residence:`, `City:`, `Area:`, `Locality:` and `Last seen:`
fields are location candidates and take precedence over statistical NER spans. The local
phrase list in `backend/data/location_names.json` (Indian states, union territories, major
cities and localities such as Bandra Kurla Complex) marks known places after NER, so a place
word cannot split a longer name such as "Goa Marine Exports". Single-word entries match only
when capitalized. Add exact place-name variants to that JSON list and restart to extend it.

`services/entity_spans.py` cleans every NER prediction before review: it drops dates, times,
amounts, bullets and form labels ("Age", "Page 1", "September 2026", "INR 3,20,000"), splits
spans at hard line breaks ("Anita Desai⏎Age"), uses explicit suffixes to fix kinds
("… Pvt. Ltd.", "… Police Station", "… Road"), and keeps one kind per name. These rules only
trim or discard source spans; they never invent names. NER can still misclassify unfamiliar
names without a suffix (for example, a telecom brand tagged as a place). Statutes and sections
("BNS 318(4)", "Bharatiya Nyaya Sanhita"), courts and the State ("State Sessions Court", "State
of Maharashtra"), ranks and FIR form labels ("Nationality", "P.S.") are never entity candidates.

`services/structural_relations.py` adds relationships an FIR states through its layout or in
fixed phrasing, without a model: people listed under an accused or witness heading
(`SUSPECT_IN`/`WITNESS_IN`), `Accused:`/`Witness:` fields, `Address:` in a person's record and
"resident of" in a clause naming one person (`RESIDES_IN`), `Place of occurrence:` (`OCCURRED_AT`),
`Nature of complaint:`/`Offence:` (`OF_TYPE`), "X called Y", "calls between X and Y", "X was seen
at/visited L" and "X, an employee of O". Every named person, organization and vehicle is
`MENTIONED_IN` the document's own FIR. Labels may be followed by their value on the same line
("Accused: …") or on the next line (table layouts). Case edges attach only to the document's own
FIR: its only case, or the only case printed under an "FIR No." label. Other FIR numbers referenced
in the text get no case edges, and a document with two labelled FIRs gets none. "FIR No." is not
part of a case ID, so "FIR No. FIR-SYN-2026-0142" and "FIR-SYN-2026-0142" are the same case.
Phrases require the words to be adjacent, so negations do not match. Each edge cites a
contiguous source span and passes the same validation as model output.

Model suggestions add to these edges. A model edge is excluded for review when its citation has no
wording for its type (a `WITNESS_IN` citation must mention a witness, for example), or when it
gives a person a different role from the FIR's own accused/witness listing.

Groq receives bounded passages surrounding entity mentions, with nearby context and
explicit markers where text was omitted. It cannot add entities, and relationships retain
the existing predicate, direction, evidence and review checks. Entity candidates with no
relationships still appear for review. The existing rate-limit backoff applies. Logs report
local entity counts, passage counts and Groq input/output token usage, without source text
unless debug responses are enabled.

Location entities keep their first detected source sentence in `evidence`, rather than just
the place name. It is visible under **Source evidence** in review, retained in the staged
extraction, and saved with the extracted entity after confirmation. Groq receives this
sentence as location context along with numbered source passages. If a batch boundary cuts
the saved sentence, a separate bounded passage preserves it. For OCR blocks without useful
sentence boundaries, evidence falls back to a source line or a maximum 2,000-character
source window around the mention. Later mentions remain available in relevant passages;
each accepted relationship has its own source evidence.

`RESIDES_IN` links a person to an explicitly stated residence; `SEEN_AT` records an explicit
sighting. `OCCURRED_AT` continues to link a case to an incident location. Mere co-occurrence
does not create any of these links. Restart FastAPI to apply the expanded SQL predicate
constraint before confirming new extractions. Existing saved records are not re-extracted.

This reduces generated entity JSON and can omit unrelated source text; token savings vary
with the document and retries. It does not eliminate Groq rate limits. The English model can
miss names or misclassify entities, and distant references or relationships across batches
may be missed. Review the results against the document. Use `EXTRACTION_MODE=groq` and
restart if you need the original extraction behavior. Custom languages require a compatible
installed spaCy model; the regex rules remain focused on Indian identifiers.

The local pipeline follows spaCy's [model loading](https://spacy.io/usage/models) and
[entity recognition](https://spacy.io/usage/linguistic-features#named-entities) interfaces.

Run the **FastAPI** backend with `python -m backend.server` from the repository root and your
virtual environment activated. The repository's `npm run server` still launches the old
Express backend, which does not implement this pipeline. Restart FastAPI after updating.

Startup applies `sql/ingestion.sql` to the existing database from the supplied dump. It adds
organizations, vehicles, extraction evidence tables, document job fields, and the `case_people`
view. It allows `cases.person_id` and `locations.state` to be null so imports do not invent a
primary suspect or an unknown state. Existing rows remain intact. Persons, cases, locations,
and crime types are inserted into the original tables; phone entities and all extracted
properties also live in `extracted_entities`. Each source relationship lives in
`extracted_relationships` and Neo4j. The Neo4j account must be able to create uniqueness
constraints as well as write nodes and edges.

Supported graph predicates are `MENTIONED_IN`, `WITNESS_IN`, `SUSPECT_IN`, `OCCURRED_AT`,
`OF_TYPE`, `EMPLOYED_BY`, `OWNS`, `CONTACTED`, `RESIDES_IN`, and `SEEN_AT`, with the requested subject/object types.
Unidentified phone owners are not turned into people or inferred `CONTACTED` edges.

Uploads return immediately with status `queued`. A persistent, single-job-per-worker queue
reports stage and batch progress to the review page and document list, refreshed every
three seconds. Percentages mark workflow milestones and completed batches, not elapsed
time estimates; an in-flight model request keeps its current percentage. Extraction reaches
100% when ready for review. Confirmation starts a separate saving phase. Progress is stored
in PostgreSQL and remains available after refreshing the page.
The queue
extracts text, calls Groq, and stops at `awaiting_review`. After confirmation it commits
PostgreSQL entity records and a graph payload in one transaction,
and then writes Neo4j in a transaction after confirmation. `complete` means both saves succeeded. A `sync_failed`
job keeps its PostgreSQL data and retries only Neo4j. Graph replay uses stable relationship
IDs to avoid duplicates. Jobs interrupted by shutdown are requeued; crash-abandoned leases
become available after 20 minutes. PostgreSQL and Neo4j are eventually consistent, not one
shared distributed transaction.

The review page requires a Yes/No choice for each entity and relationship before saving.
Rejecting an entity also excludes relationships connected to it. Rejected items and their
reasons remain in the document's review history, but are not saved as entity or graph records.
Use **Remove document** to delete a stopped, draft, or completed document, its extraction
rows, search chunks, and document-specific Neo4j links. Unshared import-created canonical
records and isolated import-created graph nodes are removed too. Shared and pre-existing
records are preserved. Processing documents must be stopped first.
Removal holds a PostgreSQL transaction until Neo4j cleanup succeeds; if Neo4j fails, the
document remains available for retry. Cleanup is idempotent if SQL commit fails after
Neo4j succeeds. Restart the backend after upgrading to install the import-ownership table.
For older data, ownership is backfilled only when the extraction ID proves the record was
created by ingestion; existing numeric location/crime rows are retained when ownership
cannot be established. Already-deleted source documents require separately reviewed
cleanup because the previous implementation removed their provenance.

The page shows status, source text, entities, relationships, and supporting quotes. Use
**Process document** to retry extraction, or **Retry Neo4j sync** after fixing graph access.
A failed extraction retry keeps OCR text but calls Groq again. Existing stored PDFs can also
be processed. Files used as extraction evidence are retained and cannot be deleted by the
ordinary document deletion endpoint.

Limits: 20 MB per file, 30 PDF pages/image frames, 60,000 extracted characters, and a ten-minute
job timeout. Long text is split into overlapping chunks. Repeated uploads remain separate
source documents. Explicit identifiers can link existing records; names alone never merge
people across documents. This does not include fuzzy identity matching or editing extracted fields.

API additions:

- `GET /api/documents/source-types`: categories and accepted file extensions.
- `POST /api/documents`: multipart `file` and `sourceType` (defaults to `fir`).
- `GET /api/documents/{id}`: owner-scoped status, extracted text, and extraction JSON.
- `POST /api/documents/{id}/process`: retry a failed/sync-failed/stored document.
- `POST /api/documents/{id}/confirm`: approve the exact staged `extraction` JSON and queue saving.

Extraction tests mock Groq and Neo4j provider calls. OCR tests run real Tesseract when installed.
The optional PostgreSQL tests create and remove isolated databases; run them only against a
test instance with a user allowed to create databases:

```bash
CNA_TEST_PGHOST=/path/to/test/socket CNA_TEST_PGPORT=55439 \
  python -m pytest backend/tests/test_ingestion_postgres.py -q
```

Implementation references: [Groq JSON output mode](https://console.groq.com/docs/structured-outputs),
[pypdfium2 resource/thread handling](https://pypdfium2-team.github.io/pypdfium2/python_api.html), and
[pytesseract setup](https://pypi.org/project/pytesseract/).

### Review before saving

New uploads open `/documents/{id}/review`. The page shows a scrollable dossier for each entity,
all extracted attributes, identifiers, source evidence, incoming/outgoing relationships, and a
complete relationship list. **Review later** leaves the draft untouched. **Confirm and save**
authorizes saving the displayed extraction to the entity tables and Neo4j.

The original file, OCR text, and draft JSON stay in the officer's document staging record so
review can resume after a refresh. No persons/cases/organizations/vehicles, extraction entity
or relationship rows, or graph nodes/edges are created before confirmation. Confirmation is
owner-scoped and checks JSON equality with the staged snapshot; stale or modified snapshots
are rejected. `confirmed_at` and `confirmed_by` record approval. Retries of an approved import
reuse that exact extraction. Previously completed imports are retained.

During review, **Reject relationship** excludes an individual suggestion; **Undo rejection**
restores it before confirmation. Controls in the entity dossiers and complete relationship
list share the same selections. Pending choices last for the current page; **Confirm and
save** records them. Entities remain in the draft even if all their relationships are rejected.
The confirmation API accepts `rejected_relationship_indices`, a list of distinct zero-based
indices into the original `extraction.relationships`. The server atomically checks ownership
and equality with that original draft, then moves selected relationships to
`excluded_relationships` with the reason `Rejected by reviewer during confirmation.`
The document's confirmation identity/time records the decision. Rejections remain in the
review history but never enter `extracted_relationships` or the Neo4j graph payload.
This applies to drafts awaiting review, not links already saved from completed documents.

The configured GPT-OSS models use Groq strict JSON schema output. Temporary rate limits use
bounded retries respecting `Retry-After`; evidence is still validated against the source.

### Local extraction with Ollama

Start the Ollama app (or `ollama serve`) and install a local model:

```bash
ollama pull qwen3:4b
```

Set these values in `backend/.env`, then restart FastAPI:

```dotenv
EXTRACTION_PROVIDER=ollama
EXTRACTION_MODE=hybrid
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:4b
OLLAMA_TIMEOUT=180
OLLAMA_MAX_TOKENS=4096
SPACY_MODEL=en_core_web_sm
```

Hybrid mode uses spaCy/regex for entity candidates and Ollama only for
sentence-based relationship extraction. Install the configured
spaCy model with `backend/.venv/bin/python -m spacy download en_core_web_sm` if needed.
`EXTRACTION_MODE=groq` is the legacy name for full model extraction; it also respects
`EXTRACTION_PROVIDER=ollama` and does not require a Groq key in that configuration.
Set `EXTRACTION_PROVIDER=groq` to switch back. Network explanation summaries still use Groq.

The backend calls Ollama's native `/api/chat` endpoint using the existing `httpx` client;
no Ollama Python package is needed. Requests use a JSON schema, `think=false`, a 16K
context window, and a ten-minute model keep-alive. All evidence and relationship checks,
correction retries, and the Yes/No review flow still apply. There is no automatic cloud
fallback. Logs show token counts and generation/load durations for comparing performance.
Truncated output retries with twice the configured output budget, capped at 8192 tokens.
`OLLAMA_MAX_TOKENS` accepts 256–8192; truncated JSON is never accepted as a complete extraction.
In hybrid Ollama mode, evidence is generated as flat `start_line`/`end_line` fields and
converted back to exact source quotes by the server. The native JSON schema restricts
each predicate to existing refs with the correct entity types and direction. Source,
endpoint-identity, and evidence-range validation still run before saving any links.
The model prompt no longer repeats the full JSON schema.

Relationship batches group
whole cue sentences; at 1,024 output tokens the target is four sentence spans and 2,048
source characters. A full sentence and its pronoun context can exceed that soft target;
neither is cut to fit. Identical sentence/context repeats are analyzed once. Single-FIR
context is retained, and omissions are marked so they cannot be joined into false quotes.
The output schema allows only nonempty evidence ranges of at most 2,000 characters and
bounds the number of returned edges by the number of possible typed endpoint pairs.
To extend relationship cues, edit `RELATIONSHIP_CUES` in
`backend/services/relationship_sentences.py`. Keyword selection can miss unfamiliar
wording, and local entity detection is not a guarantee of finding every real entity.
Requests remain sequential, with at most one correction attempt per batch; there is
no recursive retry tree and no change to investigator-chat thinking settings. If a group
still fails extraction, it can be retried once as its individual complete source sentences.
Pronoun context is preserved; an unsplittable sentence or failed individual retry stops
processing instead of silently treating a partial result as complete.
If a complete response has invalid relationships, valid relationships are retained in
memory and merged with the corrected response, so a retry cannot silently erase them.
Uncorrected suggestions remain excluded for review. Truncated or malformed JSON is retried as a whole response;
it is never accepted as a completed extraction.

To measure relationship extraction on labelled synthetic examples without writing to
either database, run from the repository root:

```bash
backend/.venv/bin/python -m backend.scripts.benchmark_relationships
```

The benchmark uses the configured local Ollama model and reports runtime, tokens,
missing/extra relationships, and errors for explicit facts, negation/shared-location
checks, and dense records. Use `--runs 3` for repeated measurements or
`--sample explicit_facts` for a quick check. It exits unsuccessfully if any expected
relationship is missing, any extra relationship appears, or extraction fails. These
synthetic checks are a regression aid, not an accuracy estimate for real FIRs.
See [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs).

### Debug Groq responses

Set `GROQ_DEBUG_RESPONSES=true` in `backend/.env` and restart FastAPI. Each extraction
attempt prints the HTTP response body to the backend console, followed by the generated
JSON or `error.failed_generation` when Groq rejects it. Output is captured before validation,
so failed attempts are visible too. API keys are redacted; request headers are never printed.
Full responses can contain source document data. Set the flag to `false` when finished.

### Reusing existing entities and reviewing person identities

New imports look up existing records before creating graph nodes. Stable source IDs are
reused; organizations/crime types use normalized names, vehicles use normalized registration,
and locations use city/state (a missing state can reuse only an unambiguous city). Imported
phone numbers ignore formatting, including equivalent Indian +91/0091 prefixes. Ambiguous
identities are not guessed. These rules prevent new duplicates; they do not consolidate old ones.

On **Confirm and save**, document review checks same-name people. If an existing person and
the extracted person share at least **three distinct, already-resolved neighbouring nodes**,
a dialog lists the shared nodes and asks whether to reuse that person or keep a separate
record. Multiple edges to one neighbour count once; direction/predicate differences do not
create additional shared neighbours. Rejected entities and relationships do not contribute.
Names alone never automatically merge people. Existing exact person IDs still resolve directly.

Suggestions combine imported SQL links and Neo4j connections. If Neo4j cannot be checked,
identity review reports an error rather than silently treating it as no match. Approved
choices are checked server-side and stored with the officer's document confirmation. Each
document retains separate source evidence, so removing one source preserves shared records.
Restart FastAPI to apply the idempotent `person_matches` column migration before using this flow.

### Investigator chat answers

Investigator questions use a separate question-led prompt for Ollama and Groq. The latest
question is the final user message; at most six recent messages from the same selected
record provide follow-up context. Previous answers are not treated as source evidence.
The provider returns two fields, rendered as **Recorded facts** and **Investigator insight**,
with a target of about 100 words total. Answers focus on the requested detail, state when
it is unknown, and separate documented facts from analytical observations. Ollama thinking
remains enabled for investigator questions. Malformed or cut-off answers report an error
rather than displaying incomplete sections.

### Detailed profile records and hybrid document retrieval

The profile's timeline is replaced by a detailed record: identity fields, cases, connected
locations, source-backed relationships, and additional extracted attributes. Stored details
load without an AI call. **Generate detailed AI record** creates a cited synthesis of those
facts and retrieved source passages. Source quotes that fail the existing person-name checks
are marked for review and excluded from the structured AI input. The model still needs human
verification; citation validation checks source IDs, not the truth of generated statements.

Confirmed document text is indexed into overlapping passages of at most 1,600 characters
with 240-character overlap, preferring sentence/paragraph boundaries. Citations use exact
one-based inclusive character ranges in the extracted text, not PDF page coordinates.
`RAG_EMBEDDING_MODEL=embeddinggemma` enables local vectors through Ollama's
[embedding API](https://docs.ollama.com/api/embed); run `ollama pull embeddinggemma` first.
Vectors are normalized and stored beside the passages in PostgreSQL `double precision[]`,
with embedding model and index-version metadata. No separate vector server or extension is
required. This implementation uses exact cosine search over accessible document vectors;
large deployments should add an indexed vector engine such as pgvector instead of a full scan.

Retrieval combines keyword and semantic rankings with reciprocal-rank fusion, suppresses
near-duplicate overlapping passages, and restricts both queries to the signed-in officer's
confirmed documents linked to the selected canonical person. A shared document can mention
several people; generated records must not attribute another person's facts to the selection.
Embeddings are built after confirmation, leaving entity/relationship extraction in batches.
If the embedding service is unavailable, keyword search continues and the profile displays
the number of passages lacking embeddings. Original documents, provenance, and graph links
remain authoritative. Deleting a document cascades to its passages and vectors.

To apply the idempotent schema migration and rebuild the index for existing confirmed text:

```sh
backend/.venv/bin/python -m backend.scripts.reindex_documents
# Or rebuild a single confirmed source:
backend/.venv/bin/python -m backend.scripts.reindex_documents --document 5
```

An index replacement is transactional. Reindexing does not rerun AI extraction or change
person/graph records. Generated records include at most 20 retrieved passages and bounded
model context; all stored profile facts remain visible even when the AI context is smaller.
Restart FastAPI after updating the backend.

Entity verification also bounds each Ollama request by both candidate count and combined
source-context size. If a long-context group still returns incomplete JSON, it is retried
per candidate; unchecked candidates are never accepted. This keeps the full context for
review while preventing one long sentence from consuming the entire response budget.

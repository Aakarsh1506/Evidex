# 🕸️ EVIDEX

React/Vite frontend with an API backed by **PostgreSQL** and **Neo4j** — available as either an **Express** backend or a **FastAPI** backend (same routes, same databases, pick one). Officer accounts are cookie/JWT authenticated, and an admin panel is used to provision new officer accounts.

![Node](https://img.shields.io/badge/node-%3E%3D22.12-brightgreen)
![Frontend](https://img.shields.io/badge/frontend-React%20%2B%20Vite-61DAFB)
![Backend](https://img.shields.io/badge/backend-Express%20%7C%20FastAPI-black)
![Database](https://img.shields.io/badge/databases-PostgreSQL%20%7C%20Neo4j-4479A1)

---

## 📚 Table of contents

- [Project structure](#-project-structure)
- [Set up — step by step (new machine, full stack)](#️-set-up--step-by-step)
- [Run locally — quick start](#-run-locally)
- [Authentication & accounts](#-authentication--accounts)
- [Per-officer data](#️-per-officer-data)
- [Groq AI summaries](#-groq-ai-summaries)
- [Environment variables](#️-environment-variables-express-backendenvexample)
- [Checks](#-checks)
- [FastAPI alternative](#fastapi-alternative)

---

## 📁 Project structure

```text
Criminal Network Analysis/
├── express-backend/
│   ├── middleware/     # Auth guards (requireAuth, requireAdmin)
│   ├── neo4j/          # Neo4j scripts and queries
│   ├── routes/         # Express route handlers
│   ├── scripts/        # CLI utilities (e.g. add-officer)
│   ├── services/       # Business logic, incl. Groq integration
│   ├── sql/            # Reference SQL for hand-managed setup
│   ├── uploads/        # Uploaded PDFs on disk (gitignored)
│   ├── utils/          # Shared backend helpers
│   ├── .env            # Local environment variables (gitignored)
│   ├── .env.example    # Template for required env vars
│   ├── db.js           # PostgreSQL connection
│   ├── neo4jDriver.js  # Neo4j driver setup
│   └── server.js       # Express app entry point
│
├── backend/
│   ├── middleware/, routes/, services/, sql/, utils/  # Python equivalents of the above
│   ├── neo4j/           # Same Neo4j scripts, shared reference with express-backend/
│   ├── uploads/         # Uploaded PDFs on disk (gitignored)
│   ├── tests/           # pytest suite, incl. fixtures asserting parity with Express
│   ├── .env             # Local environment variables (gitignored) — separate from express-backend/.env
│   ├── .env.example     # Template for required env vars
│   ├── db.py            # PostgreSQL connection
│   ├── neo4j_driver.py  # Neo4j driver setup
│   ├── app.py           # FastAPI app factory
│   └── server.py        # FastAPI entry point (`python -m backend.server`)
│
├── frontend/
│   ├── public/          # Static assets (images, etc.)
│   ├── src/
│   │   ├── api/          # API client functions
│   │   ├── components/   # Reusable React components
│   │   └── pages/        # Route-level page components
│   ├── index.html
│   └── vite.config.js
│
├── node_modules/        # Installed dependencies (gitignored)
├── .env                 # Root-level environment variables (gitignored)
├── .gitignore
├── .oxlintrc.json
├── package-lock.json
├── package.json
└── README.md
```

| Folder | What's in it |
|---|---|
| `frontend/` | React source (`src/`), static assets (`public/`), HTML entry point, and Vite configuration. Builds output to `frontend/dist/`. |
| `express-backend/` | Express server, routes, middleware, services, utilities, database connections, and Neo4j scripts (`neo4j/`). |
| `backend/` | FastAPI equivalent of the above, same API routes and database schemas. See [`backend/README.md`](backend/README.md) for its own setup/run/verify instructions. |

Shared npm dependencies, scripts, and lint configuration live at the **repository root**. Run all commands below from the root unless noted otherwise.

---

## 🛠️ Set up — step by step

> Full walkthrough for a **new machine**: FastAPI backend (`backend/`), React frontend, and the local AI pipeline (spaCy + Ollama). Commands are for macOS; Windows/Linux differences are called out inline. Run every command from the repository root unless a step says otherwise.

### Step 0 — Gather what Git doesn't carry (on the *old* laptop)

| # | Task | Command |
|---|---|---|
| 1 | Commit & push the code, or copy the whole project folder — uncommitted work isn't in Git. | — |
| 2 | Copy `backend/.env` privately (USB drive, password manager). It holds passwords and the JWT secret. **Never commit it.** | — |
| 3 | Export the PostgreSQL database. The app needs the existing `persons`, `cases`, `locations` and `crime_types` tables; the backend does not create them. | `pg_dump -Fc -d criminal_network -f criminal_network.dump` |
| 4 | Copy the custom spaCy model if you use it — `spacy_crime_multientity_ner_package/output/model-best` (~420 MB, gitignored). You can also retrain it in Step 7, or use a standard spaCy model instead. | — |
| 5 | Uploaded files are stored **in the database**, so they move with the dump. Documents uploaded *before* that change may exist only in `backend/uploads/` — copy those in first. | `backend/.venv/bin/python -m backend.scripts.migrate_uploads` |
| 6 | **Neo4j:** if `NEO4J_URI` starts with `neo4j+s://…databases.neo4j.io` (Neo4j Aura, cloud), the new laptop reuses the same credentials — nothing to copy. | — |

### Step 1 — Install the prerequisites

| Tool | Version | macOS (Homebrew) | Windows / Linux |
|---|---|---|---|
| Git | any | `brew install git` | git-scm.com / package manager |
| Node.js | 22.12+ | `brew install node` | nodejs.org installer |
| Python | 3.11–3.13 (tested on 3.13) | `brew install python@3.13` | python.org (tick "Add to PATH") |
| PostgreSQL | 16+ | `brew install postgresql@16 && brew services start postgresql@16` | postgresql.org installer / `apt install postgresql` |
| Tesseract OCR | any | `brew install tesseract` | UB Mannheim build (Windows) / `apt install tesseract-ocr` |
| Ollama | latest | download from ollama.com | ollama.com |

Verify everything installed correctly:

```bash
node --version && python3 --version && psql --version && tesseract --version && ollama --version
```

### Step 2 — Get the code and install JavaScript packages

```bash
git clone https://github.com/Aakarsh1506/Criminal-Network-Analysis.git
cd Criminal-Network-Analysis
npm install
```

### Step 3 — Create the Python environment

```bash
python3 -m venv backend/.venv
source backend/.venv/bin/activate          # Windows: backend\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
```

This installs FastAPI, spaCy, and the small English model `en_core_web_sm`. **Keep this terminal's environment activated** for the backend steps below.

### Step 4 — Restore the PostgreSQL database

```bash
createdb criminal_network
pg_restore --no-owner -d criminal_network criminal_network.dump
```

> **Missing `postgis` extension or `geometry` type?** Install PostGIS (`brew install postgis`), run `psql -d criminal_network -c "CREATE EXTENSION postgis;"`, then repeat the restore into a freshly created database. On first start, the backend adds its own tables (officers, documents, extraction and workspace tables) from `backend/sql/`.

### Step 5 — Set up Neo4j

- **Aura (cloud):** nothing to do — reuse the URI, user, and password from the old `backend/.env`.
- **New empty Neo4j database:** in Neo4j Browser, run **in this order**:
  1. `backend/neo4j/schema.cypher`
  2. `backend/neo4j/import_data.cypher`
  3. `backend/neo4j/synthetic_relationships.cypher` *(demo links only)*

  The account must be allowed to create constraints.

### Step 6 — Install the local AI models (Ollama)

Start the Ollama app (or run `ollama serve`), then:

```bash
ollama pull qwen3:1.7b        # relationship extraction and investigator answers
ollama pull embeddinggemma    # document search for the AI investigator
```

> 💡 `qwen3:4b` gives better answers but is slower. If your laptop has **16 GB+ RAM**, pull it instead and set `OLLAMA_MODEL=qwen3:4b`.

### Step 7 — Choose the spaCy entity model

Pick **one**:

| Option | How |
|---|---|
| Copied custom model | Place the folder at `spacy_crime_multientity_ner_package/output/model-best` |
| Retrain it (~10–30 min on CPU, downloads `en_core_web_lg`) | `bash spacy_crime_multientity_ner_package/train_model.sh` |
| Standard model, no training (more accurate) | `python -m spacy download en_core_web_lg` |
| Standard model, no training (already bundled) | keep `en_core_web_sm` |

### Step 8 — Create `backend/.env`

Copy the old laptop's `backend/.env`, or start from the template:

```bash
cp backend/.env.example backend/.env
```

Then check these values:

```dotenv
# PostgreSQL on this laptop — or instead set one URL, e.g. from Render:
# DATABASE_URL=postgresql://user:password@host:5432/criminal_network
PGHOST=localhost
PGPORT=5432
PGUSER=your_mac_or_postgres_user
PGPASSWORD=
PGDATABASE=criminal_network

# Neo4j (same as before for Aura)
NEO4J_URI=neo4j+s://your-instance-id.databases.neo4j.io
NEO4J_USER=your_user
NEO4J_PASSWORD=your_password

# Local AI pipeline
EXTRACTION_PROVIDER=ollama
EXTRACTION_MODE=hybrid
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:1.7b
OLLAMA_TIMEOUT=180
OLLAMA_MAX_TOKENS=4096
RAG_EMBEDDING_MODEL=embeddinggemma

# spaCy: an ABSOLUTE path on THIS laptop, or en_core_web_lg / en_core_web_sm
SPACY_MODEL=/Users/you/path/to/Criminal-Network-Analysis/spacy_crime_multientity_ner_package/output/model-best

# Auth: keep the old JWT_SECRET to keep sessions compatible, or generate a new one with
#   python3 -c "import secrets; print(secrets.token_hex(48))"
JWT_SECRET=replace_with_a_long_random_string
ADMIN_USERNAME=admin
ADMIN_PASSWORD=choose_a_strong_password
PORT=5050
FRONTEND_ORIGIN=http://localhost:3000
NODE_ENV=development
```

> ⚠️ **`SPACY_MODEL` is the setting most often wrong after a move** — the old laptop's absolute path does not exist on the new one.

### Step 9 — Create an officer login

The admin account (`ADMIN_USERNAME` / `ADMIN_PASSWORD`) can create officers from `/admin`. Or, with the virtual environment active:

```bash
python -m backend.scripts.add_officer --username jdoe --name "Jane Doe" --org "Nandipur Police" --dob 1990-05-14
```

It prompts for the password.

### Step 10 — Start everything

Use **two terminals**, both in the repository root, with Ollama running:

```bash
# Terminal 1 — backend (port 5050)
source backend/.venv/bin/activate          # Windows: backend\.venv\Scripts\activate
python -m backend.server
```

```bash
# Terminal 2 — frontend (port 3000)
npm run dev
```

Open **http://localhost:3000** and log in. The first document extraction is slower while spaCy and the Ollama model load.

### Try the database import

Upload `docs/sample_database_export.sql` on the Upload page with source **Database export**. Its
synthetic rows become 15 records and 10 relationships in the review screen; nothing is saved until
you confirm. Statements in an uploaded file are read as data and never executed.

### Step 11 — Check that it works

```bash
curl http://localhost:5050/api/health     # {"ok":true}
python -m pytest backend/tests -q         # backend tests; no database or AI provider needed
```

### 🧩 Troubleshooting

| Symptom | Fix |
|---|---|
| `Hybrid extraction needs spaCy and its model` | `SPACY_MODEL` path is wrong or the model isn't installed (Step 7–8). Restart the backend. |
| `Ollama model not found` | Run `ollama pull` for the model named in `OLLAMA_MODEL`. |
| `Unable to reach Ollama` | Open the Ollama app or run `ollama serve`. |
| `Install Tesseract on the server` | Install Tesseract (Step 1) and restart the backend. |
| `Document embeddings are unavailable` | `ollama pull embeddinggemma`, or leave `RAG_EMBEDDING_MODEL` empty to use keyword search only. |
| Login fails for everyone | Wrong database or `JWT_SECRET`; check `backend/.env` and restart. |
| Port 5050 or 3000 already in use | Stop the other process (`lsof -i :5050`) or change `PORT` in `backend/.env` and the proxy target in `frontend/vite.config.js`. |
| Graph pages show connection errors | Check `NEO4J_URI`, user, and password; Aura instances pause when idle and must be resumed in the Aura console. |
| `.env` changes have no effect | The backend reads `.env` only at start; stop and restart it. |

---

## 🚀 Run locally

> Quick-start version of the setup above — use this if you already have prerequisites and databases in place.

Use **Node.js 22.12 or newer**. Install dependencies with:

```bash
npm install
```

Create `express-backend/.env` using `express-backend/.env.example` if you don't already have it, then configure your PostgreSQL and Neo4j connections (see [Environment variables](#️-environment-variables-express-backendenvexample) for the full list).

Run the frontend and backend in **separate terminals**:

```bash
npm run server   # starts the Express API
```

```bash
npm run dev      # starts the Vite dev server
```

Open **http://localhost:3000**.

### Running the FastAPI backend instead

Same frontend, same port, same databases — only the backend terminal command changes. Requires **Python 3.11+**.

1. Create and activate a virtual environment for it, then install dependencies:
   ```bash
   python3 -m venv backend/.venv
   source backend/.venv/bin/activate   # Windows: backend\.venv\Scripts\activate
   python -m pip install -r backend/requirements.txt
   ```
2. Create `backend/.env` using `backend/.env.example` if you don't already have it, then configure it — this is a **separate file** from `express-backend/.env`, even if you're pointing both at the same databases.
3. With the virtual environment still active, start the API:
   ```bash
   npm run server:fastapi   # starts the FastAPI API (python3 -m backend.server)
   ```
   ```bash
   npm run dev               # starts the Vite dev server, same as above
   ```

Open **http://localhost:3000** — same URL either way. See [`backend/README.md`](backend/README.md) for the full setup/run/verify reference, including the `add-officer` CLI equivalent (`npm run add-officer:fastapi`).

---

## 🔐 Authentication & accounts

Every API route except `/api/auth/login` and `/api/health` requires a valid session cookie (`requireAuth`). There are two kinds of accounts:

### Officer accounts

Stored in the `officers` table, password hashed with bcrypt. Created either:

- **Through the admin panel** (`/admin`, see below) — the normal path for a real org.
- **Via the CLI script**, useful for bootstrapping the very first account on a fresh deployment:
  ```bash
  npm run add-officer -- --username jdoe --password "SomeStrongPass!" --name "Jane Doe" --org "Delhi Police"
  ```

An officer's session is scoped to their `officer_id` everywhere it matters — pinned criminal, working list, and uploaded documents are all private to that officer (see [Per-officer data](#️-per-officer-data)).

### Admin account

A single hardcoded account, checked against `ADMIN_USERNAME` / `ADMIN_PASSWORD` in your backend's `.env` (`express-backend/.env` or `backend/.env`, depending which backend you're running) — **not** a row in the `officers` table. Logging in with these credentials on the normal login page redirects to `/admin` instead of `/dashboard`.

From `/admin` you can:

- Create new officer accounts (username, password, name, DOB, org).
- View all existing officers and deactivate one (soft-delete via `is_active`, not a hard delete — keeps history intact).

> ⚠️ **This is a stopgap for one deployment/demo.** It's a single shared password with no rotation and no audit trail. Before a real multi-org deployment, this should become a proper `role = 'admin'` row in `officers` (bcrypt-hashed like everyone else), ideally with a separate "platform" tier above it that provisions each org's first admin — see project notes for the fuller plan.

---

## 🗂️ Per-officer data

Three things are scoped to the logged-in officer's `officer_id`, each backed by its own self-creating table (no manual migration needed — they're created with `CREATE TABLE IF NOT EXISTS` the first time the backend boots):

| Feature | Table | Notes |
|---|---|---|
| Pinned criminal (Dashboard) | `officer_pinned_criminal` | One row per officer, replaced on re-pin |
| Working list (Dashboard / Criminal List) | `officer_working_list` | Many rows per officer |
| Uploaded documents (Upload page) | `officer_documents` | Files stored on disk in `express-backend/uploads/` (or `backend/uploads/` for FastAPI), metadata + ownership in Postgres |

None of this is shared across officers — each of these used to be `localStorage`-based (or in-memory, for documents) and was visible to *whoever was using the browser*, not the logged-in officer. All three now go through authenticated, officer-scoped API routes instead.

---

## 🤖 Groq AI summaries

1. Create an API key at [console.groq.com/keys](https://console.groq.com/keys).
2. Add `GROQ_API_KEY=your_key` to your backend's `.env` (`express-backend/.env` or `backend/.env`). Keep existing database settings.
3. Restart the backend (`npm run server` or `npm run server:fastapi`).
4. Open a profile and click **Explain this network** below its graph.

The optional `GROQ_MODEL` setting defaults to `openai/gpt-oss-20b`. The Express backend calls the [Groq Chat Completions API](https://console.groq.com/docs/api-reference) using Node's built-in `fetch`; the FastAPI backend uses `httpx`. Neither needs an additional SDK.

> ⚠️ **Never place the key in frontend code or a `VITE_` variable.** Backend `.env` files are ignored by Git.

### `POST /api/criminals/:id/explain`

- Requires a valid officer/admin session, same as the rest of the API.
- Reads records from the databases and sends the profile ID/name/status, up to 50 cases, and 25 graph overlap rows to Groq.
- Returns `{ explanation }`.
- Photos and demographic fields are excluded.
- Generation happens only on a button click.
- The response explains **shared attributes**, not proven personal associations or guilt.
- Empty overlap results may mean Neo4j was unavailable. Summaries require source verification.

**Limits & safety:**

- Requests have a 30-second Groq timeout and a process-wide limit of **three concurrent summaries**.
- Missing keys, provider failures, and usage limits produce actionable UI errors.

---

## ⚙️ Environment variables (`express-backend/.env.example`)

The FastAPI backend (`backend/.env.example`) uses the same variable names — copy whichever backend's example file you're running to a real `.env` in that same folder. **Each backend reads its own `.env`; they don't share one.**

```dotenv
PGHOST=localhost
PGPORT=5432
PGUSER=postgres
PGPASSWORD=your_password_here
PGDATABASE=criminal_network
PORT=5050

NEO4J_URI=neo4j+s://your-instance-id.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_aura_password_here

# Groq AI summaries (server only)
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-20b

# Auth
# Generate a real secret with: node -e "console.log(require('crypto').randomBytes(48).toString('hex'))"
JWT_SECRET=replace_with_a_long_random_string
JWT_EXPIRES_IN=12h
COOKIE_NAME=cna_token
# Set to your deployed frontend URL in production (dev works out of the box via the Vite proxy)
FRONTEND_ORIGIN=http://localhost:3000
NODE_ENV=development

# Admin panel login — a single hardcoded account, not stored in the
# officers table. Change these before any real deployment; there's no
# UI to change them yet, only this file.
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change_this_admin_password
```

### Deployment notes

#### Vercel frontend

Deploy from the **repository root**, where `package.json` and `vercel.json` live. Use these project settings:

| Setting | Value |
|---|---|
| Root Directory | Repository root (leave blank) |
| Framework Preset | Vite |
| Build Command | `npm run build` |
| Output Directory | `frontend/dist` |

The build script runs `vite build frontend`, so its output is `frontend/dist`, not a root-level `dist` directory. The checked-in `vercel.json` sets the build command and output directory and serves `index.html` for React page routes such as `/login` and `/dashboard`. Commit and push this configuration, then deploy that commit. See Vercel's [output directory configuration](https://vercel.com/docs/project-configuration/vercel-json#outputdirectory) and [Vite SPA routing](https://vercel.com/docs/frameworks/frontend/vite#using-vite-to-make-spas).

This configuration deploys the frontend. The app calls `/api/...`; deploy the backend separately and configure a Vercel rewrite from `/api/:path*` to your deployed backend's `/api/:path*` URL. The SPA fallback excludes `/api` so API requests are not served HTML. The localhost proxy in `frontend/vite.config.js` only runs during local development.

| Scenario | What to do |
|---|---|
| **Frontend/backend on different domains** | Set `NODE_ENV=production` so cookies get `secure: true`, and set `sameSite` to `"none"` in `express-backend/routes/auth.js`'s `COOKIE_OPTIONS` — `"lax"` (the local-dev default) gets silently dropped cross-domain. Point `FRONTEND_ORIGIN` at your exact deployed frontend URL; CORS needs it to match exactly. |
| **Managed Postgres provider (e.g. Render)** | The FastAPI backend accepts a single `DATABASE_URL` in `backend/.env`; when set, it replaces `PGHOST`/`PGPORT`/`PGUSER`/`PGPASSWORD`/`PGDATABASE`. Use Render's **External Database URL** when the backend runs elsewhere, or the **Internal Database URL** when the backend is a Render service in the same region. SSL is tried first by default; append `?sslmode=require` to insist on it. To move existing data: `pg_dump` (matching your local server's major version) then `pg_restore --no-owner --no-acl -d "$DATABASE_URL" criminal_network.dump`. |
| **Neo4j by raw IP instead of a domain** | Public CAs won't issue certificates for bare IPs, so you'll be stuck with a self-signed certificate. Node's TLS stack may tolerate that as-is, but Python's `ssl` module won't — `backend`'s driver needs its URI scheme rewritten from `neo4j+s://`/`bolt+s://` to `neo4j+ssc://`/`bolt+ssc://` to skip certificate verification. Prefer a real domain + CA-signed cert (or Neo4j Aura, which provides one automatically) wherever possible instead. |

---

## ✅ Checks

```bash
npm run build
npm run lint
node --test express-backend/services/groq.test.js
```

For the FastAPI backend, see [`backend/README.md`](backend/README.md#verify) for its `pytest`/`ruff` equivalents.

---

## FastAPI alternative

The Python backend is in [`backend/`](backend/README.md). It preserves the existing API routes and frontend proxy port. Follow its setup instructions, activate `backend/.venv`, then run `npm run server:fastapi` from the repository root.

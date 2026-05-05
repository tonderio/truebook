# TrueBook — Operations Manual

A reference for running monthly Banregio reconciliation closes, debugging stuck runs, and shipping changes safely. Targeted at the engineer-of-record (you, today; whoever inherits the project, tomorrow).

This is a living doc — when something breaks in a way you didn't expect, add a section.

---

## 1. Running a monthly close

### 1.1 The happy path (10 minutes)

1. **Create a corrida** in Contabilidad (`Nueva corrida contable`):
   - Period: `Año=2026, Mes=Abril`
   - Cuenta: `Banregio` (default)
   - Adquirentes: leave defaults

2. **Upload source files** in the corrida's detail page:
   - **Banregio statement** — `repMovimientoCuentas_*.csv` (downloaded from Banregio's online portal)
   - **Kushki SRs** — daily `TONDER_YYYY-MM-DD.xlsx` files (one per business day; 20–22 per month). If `KUSHKI_SFTP_ENABLED=true` on Railway, the pipeline auto-downloads them, otherwise upload manually
   - **FEES file** (optional but recommended) — `FEES_{MES}_{AÑO}_FINAL.xlsx` from FinOps. Without it the v2 report's OXXOPay/STP/Bitso "Neto a Liquidar" column reads $0

3. **Click "Ejecutar proceso"** (top-right). Pipeline runs through 9 stages:
   - 1–4: extract Tonder transactions/withdrawals/refunds from MongoDB, compute fees
   - 5: parse Kushki SRs (auto-downloaded or manually uploaded)
   - 5b: pull Bitso deposits via API (if `BITSO_API_ENABLED=true` and the API key covers the period)
   - 6: parse Banregio statement
   - 7: run `fees`, `kushki_daily`, and `kushki_vs_banregio` conciliations
   - 8: auto-classify all Banregio movements into 12 categories
   - 8b: re-run `kushki_vs_banregio` with classifications populated
   - 9: generate alerts

4. **Wait for status `completed`** (1–3 minutes typical). Coverage should be `100%` and the Re-clasificar / FEES-pendiente badges should be calm.

5. **Promote to reconciled** — click "Reconcile" or POST `/reconcile`. Blockers surface if:
   - Coverage < 100%
   - Pending adjustments
   - Conciliation deltas not covered by approved adjustments

6. **Download the v2 report** — click "Reporte v2". You get `RECONCILIACION_BANREGIO_{MES}_{AÑO}_v2.xlsx`. An audit copy is persisted to `uploads/{process_id}/reports/`.

### 1.2 Verifying a close before sign-off

```bash
cd Backend
python -m scripts.audit_run --process-id <ID>
```

Reads `docs/audits/{period}_process{id}.md`. Verdict at the top — `✅ PASS` or `❌ FAIL` with a list of blockers.

The audit re-runs every parse / conciliation / classification independently and cross-checks against what's stored. Section 7 (added recently) detects stale persisted v2 report files vs the current canonical output.

---

## 2. Debugging stuck or wrong runs

### 2.1 First move, every time

```bash
cd Backend
python -m scripts.diagnose_process --process-id <ID>
```

Dumps the full state of the run — files, result tables, classification distribution, last 50 ProcessLog entries — and ends with a verdict block that names the most likely failure mode.

This script is read-only and safe to run anywhere. **Run it before doing anything else.**

### 2.2 "Report shows 0% coverage"

Cause is almost always one of:
- **Pipeline never ran** → status=pending, no classifications. Click `Ejecutar proceso`.
- **Stage 8 (auto-classify) raised** → ProcessLog has an `error`-level entry under stage `classification`. Read the message; usually a parser drift bug. Fix, then `/reclassify`.
- **Files uploaded but pipeline interrupted** → status=running stuck, or status=failed with `error_message`. Re-run the pipeline.

The new endpoint **`POST /api/processes/{id}/reclassify`** (or "Re-clasificar" button) re-runs only Stage 8 + Stage 8b against the existing parsed data — no Mongo / SFTP / FEES re-fetch. Idempotent.

### 2.3 "v2 report shows wrong numbers / missing columns"

Two causes:
- **Stale persisted file**: The user downloaded an older copy. Section 7 of `audit_run.py` flags this. Fix: regenerate by hitting `/banregio-report-v2` again.
- **Missing FEES file**: Sheet 2's OXXOPay/STP/Bitso "Neto a Liquidar" reads $0 because per-merchant fee data isn't available. Fix: upload `FEES_{MES}_{AÑO}_FINAL.xlsx`, then `/reclassify`, then regenerate.

### 2.4 "kushki_vs_banregio shows 0 matches"

Was a real bug as of commit `d24d88b` (now fixed). If you see this on a run from BEFORE that commit:
- Click `Re-clasificar` — Stage 8b's classification-aware matcher will populate matches correctly.
- Then regenerate v2 report.

### 2.5 "AFUN $250 (or similar small unexplained credit)"

Kushki's reported `Depósito Neto` for AFUN occasionally exceeds the formula sum by ~$250. Confirmed not a code bug — likely a flat fee Kushki applies out-of-band.

To resolve: create + approve a `RunAdjustment`:

```python
from app.database import SessionLocal
from app.models.adjustment import RunAdjustment
from datetime import datetime, timezone, date

db = SessionLocal()
adj = RunAdjustment(
    process_id=<ID>,
    adjustment_type="ACQUIRER_ERROR",
    direction="ADD",
    amount=250.00,
    currency="MXN",
    affects="delta",
    conciliation_type="kushki_daily",
    merchant_name="AFUN",
    adjustment_date=date(2026, <MM>, <DD>),
    description="AFUN — unexplained +$250 credit in Kushki Depósito Neto. Track with Kushki account manager if recurring.",
    created_by=1,
    status="approved",
    reviewed_by=1,
    reviewed_at=datetime.now(timezone.utc),
)
db.add(adj); db.commit()
```

Then click `Reconcile` — the blocker check sees the approved adjustment and lets the run promote.

### 2.6 "Bitso section shows '$0 / no Bitso source data' in the v2 report"

The Bitso API key on Railway is scoped to a specific window (typically just one month). If you're closing a different month, the API returns 0 deposits. The report still classifies Banregio's `bitso_acquirer` movements correctly — only the per-merchant cuadre lacks the FEES side.

Two paths:
- Get an API key with broader history from Bitso ops
- Treat the cuadre as informational for periods outside the API window

---

## 3. Shipping changes

### 3.1 Branches + commits

We work on `main` directly. Each logical change → one commit with a clear message describing what AND why.

### 3.2 Local checks before push

```bash
cd Backend
source .venv/bin/activate

# 1. Pytest (always — 46 cases, <1s)
pytest tests/

# 2. March audit regression (catches spec drift)
python -m scripts.audit_run --process-id 5

# 3. (frontend changes) JSX parses cleanly
cd ../Front
node -e "
const esbuild = require('esbuild');
esbuild.build({entryPoints: ['src/pages/ProcessDetail.jsx'], bundle: false, loader: {'.jsx':'jsx'}, write: false, logLevel:'error'})
  .then(()=>console.log('✅ parses')).catch(e=>process.exit(1))
"
```

### 3.3 Deploy

`git push origin main` — Railway auto-deploys both `truebook` (Backend) and `truebook-web` (Frontend) services. Typical build: 3–5 minutes.

```bash
# Watch the deploy
gh repo view tonderio/truebook --web   # Railway dashboard linked from there
```

### 3.4 Rollback

```bash
git revert <commit-sha>
git push origin main
```

Railway redeploys the revert commit. No "rollback button" — git revert is the path.

### 3.5 Database migrations

Alembic is configured but rarely needed. New columns / tables:

```bash
cd Backend
alembic revision --autogenerate -m "<description>"
# Review the generated file — autogenerate misses some things
alembic upgrade head            # local
# Production: Railway runs `alembic upgrade head` automatically on deploy via start.sh
```

---

## 4. Where things live

### 4.1 Backend (`Backend/`)

| Path | What |
|---|---|
| `app/main.py` | FastAPI app + global exception handler |
| `app/routers/` | HTTP endpoints (auth, processes, files, results, banregio_report, etc.) |
| `app/services/` | Business logic (parsers, classifier, conciliation engine, alert engine, report builder) |
| `app/services/banregio_report_v2/` | The 3-sheet xlsx report module |
| `app/models/` | SQLAlchemy models |
| `app/schemas/` | Pydantic request/response schemas |
| `scripts/audit_run.py` | Cross-source audit (run before sign-off) |
| `scripts/diagnose_process.py` | Read-only triage tool (run when something looks wrong) |
| `scripts/generate_banregio_report.py` | CLI for the v2 xlsx |
| `tests/` | Pytest suite (46 cases) — NaN-poisoning robustness |
| `alembic/` | DB migrations |
| `uploads/{process_id}/` | Stored uploaded files (gitignored) |
| `uploads/{process_id}/reports/` | Persisted audit copies of v2 reports |

### 4.2 Frontend (`Front/`)

| Path | What |
|---|---|
| `src/pages/Contabilidad.jsx` | List + create-corrida modal (the main entry) |
| `src/pages/ProcessDetail.jsx` | Single corrida — uploads, run, reconcile, reports |
| `src/pages/SftpModule.jsx` | SFTP connection status / test |
| `src/api/client.js` | Axios client + per-domain API wrappers |
| `server.js` | Express static server (production only) |
| `vite.config.js` | Dev proxy: `/api` → `localhost:8000` |

### 4.3 Generated artifacts (gitignored, regenerable)

| Path | What |
|---|---|
| `Backend/uploads/` | User-uploaded files |
| `docs/audits/*.xlsx` | Generated v2 reports (kept for the latest only) |
| `docs/audits/*.md` | Audit run outputs (in git, useful for tracking drift over time) |
| `Front/dist/` | Vite build output |

---

## 5. Environment + secrets

### 5.1 Where they live

| Where | What |
|---|---|
| `Backend/.env` (gitignored) | Local DB URL, Mongo URI, JWT secret, Bitso API creds |
| Railway → `truebook` service → Variables | Production equivalents (separate from local) |
| Railway → `truebook-web` service → Variables | Frontend URL config (`VITE_API_URL` baked into build) |

### 5.2 Critical envs

| Var | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection (Railway-managed) |
| `MONGO_URI` | Tonder Atlas read-replica (read-only) |
| `SECRET_KEY` | JWT signing — rotate on takeover |
| `BITSO_API_KEY` / `BITSO_API_SECRET` | SPEI v2 API |
| `BITSO_API_ENABLED` | `true` to enable Stage 5b |
| `KUSHKI_SFTP_ENABLED` | `true` to auto-download Kushki SRs |

### 5.3 Rotating after a handoff

1. Railway dashboard → `truebook` → Variables → rotate `SECRET_KEY` (forces all JWTs to expire — clean break)
2. Postgres password rotation: Railway → Postgres → Settings → reset password, copy new connection string into `DATABASE_URL`
3. Bitso creds: ask Bitso ops to revoke the old key, issue a new one, paste into Railway
4. GitHub: revoke departed devs from `tonderio/truebook` collaborators

---

## 6. Domain rules to remember

(Lifted from `CLAUDE.md` and prior memory — these bite if you forget.)

### 6.1 MongoDB dedup is non-negotiable

Every Mongo query that counts transactions MUST dedupe by `payment_id` (group + sort by `created` desc + take first). One `payment_id` = one user deposit intent; retries are NOT separate transactions.

### 6.2 Acquirer field

Filter on `acq`, NOT `provider`. Cards = `kushki + unlimit` (combined). APMs = `bitso + stp + oxxopay + mercadopago + safetypay`.

Treat `provider: tonder` + `provider: guardian` as ONE performance — Guardian is anti-fraud, not a separate processor.

### 6.3 Status field

Mongo `status` is mixed-case (`Success` AND `SUCCESS`). Always `$toLower` it.

### 6.4 Withdrawals collection quirks

`usrv-withdrawals-withdrawals`:
- amount at `$monetary_amount.amount` (Decimal128), NOT `$amount`
- `business_id` is a **string** here, but a **number** in transactions
- No `business_name` field — must join `business_business`

### 6.5 Banregio classifier

12 movement types, CLABE-first detection. Full reference: `~/.claude/projects/-Users-yuyo/memory/truebook_banregio_labels.md`.

When a new Banregio statement format drops, expect 1–2% of movements to land as `unclassified` — add new keyword/CLABE rules to `auto_classifier.py` and run `/reclassify` (no full pipeline re-run needed).

### 6.6 Spanish in UI, English in code

UI copy and report headers in Spanish. Variable names, comments, commit messages in English.

---

## 7. Known limitations + open issues

### 7.1 Limitations

- **Bitso API key window** — typically scoped to one month. Plan v2 reports for non-current months knowing the Bitso section will be `(no Bitso source data)`.
- **AFUN $250 anomaly** — Kushki's `Depósito Neto` runs $250 high on AFUN occasionally. Cause unknown. Operationally handled via `RunAdjustment`.
- **Adjustments approval is honor-system in production** — backend enforces 2-eye rule (creator ≠ approver), but with one user account that's a single point of trust. Phase 1 acceptable; Phase 2 needs more identities.

### 7.2 Out-of-scope tickets (parking lot)

- GitHub Actions workflow for pytest — exists at `.github/workflows/test.yml` locally, awaits `workflow` scope on the gh token to push
- Multi-bank support (Santander, BBVA accounts) — Phase 2
- WhatsApp / email notifications on close completion — Phase 3
- AI-powered classifier suggestions for `unclassified` rows — Phase 3+

### 7.3 If something looks weird in the v2 report

Run audit Section 7. If it says the persisted file is stale, regenerate. If it says everything is fresh and the numbers still look wrong, run `diagnose_process` and read the verdict block — that's the fastest path to root cause.

---

## 8. Quick command reference

```bash
# Local dev
cd Backend && uvicorn app.main:app --reload --port 8000
cd Front && npm run dev

# Tests
cd Backend && pytest tests/

# Audit a run
cd Backend && python -m scripts.audit_run --process-id 5

# Diagnose a stuck run
cd Backend && python -m scripts.diagnose_process --process-id 5

# Generate v2 report (CLI)
cd Backend && python -m scripts.generate_banregio_report --process-id 5

# Migrations
cd Backend && alembic upgrade head
cd Backend && alembic revision --autogenerate -m "<msg>"

# Production sanity check
curl https://truebook-production.up.railway.app/health

# Login (production)
curl -X POST https://truebook-production.up.railway.app/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"yuyo@tonder.io","password":"<pw>"}'
```

---

## 9. People + context

- **Owner**: yuyo@tonder.io (you, post-handoff May 2026)
- **Stakeholders**: FinOps Tonder (define spec, consume v2 reports)
- **External vendors**: Kushki (SFTP, Acquirer), Bitso (SPEI v2 API), Pagsmile (OXXOPay), STP, Unlimit
- **Bank**: Banregio — TRES COMAS S.A.P.I. DE C.V., CLABE 058580000150650461

---

## 10. When to update this doc

- Every time a new failure mode is found and resolved (add to §2)
- Every time a new env var is required (add to §5)
- Every time the column layout / spec changes (note in §7.1 limitations)
- Every time a new ops command becomes routine (add to §8)

The point isn't perfect coverage — it's that future-you spends 2 minutes reading instead of 2 hours re-tracing.

# CLAUDE.md — Truebook (FinOps Reconciliation)

## What this is
Truebook is Tonder's accounting close / reconciliation platform. Demo flow:
Login → create run → upload Kushki CSV/Excel + Banregio PDF → execute → monitor → view FEES + reconciliations.

## Stack — dual codebase

| Area | Path | Stack |
|---|---|---|
| Backend API | `Backend/` | Python 3.11, FastAPI, SQLAlchemy, Alembic, PostgreSQL (Railway), MongoDB Atlas (pymongo + motor) |
| Frontend SPA | `Front/` | React 18, Vite, Tailwind, Tremor, TanStack Query, Recharts |
| Vercel ASGI entry | `api/index.py` | Thin wrapper over Backend FastAPI app |
| Next.js app (newer) | `apps/web/` | Next.js 15, tRPC, Prisma, `@anthropic-ai/sdk` — still early |

Both stacks coexist. Default to `Backend/` + `Front/` unless the task explicitly targets `apps/web/`.

## Dev commands

```bash
# Backend
cd Backend && uvicorn app.main:app --reload --port 8000

# Frontend (SPA)
cd Front && npm run dev            # Vite, port 3000

# Next.js app (experimental)
cd apps/web && npm run dev
cd apps/web && npx prisma db:push
cd apps/web && npx prisma studio

# Migrations
cd Backend && alembic upgrade head
cd Backend && alembic revision --autogenerate -m "msg"
```

## Deploy
- **Frontend** → Vercel (see `vercel.json`, builds `Front/dist/`, SPA rewrites to `/index.html`).
- **Backend** → Railway (PostgreSQL + Python service; env vars live on Railway).
- `api/index.py` exists so the FastAPI app can also run as a Vercel serverless function if needed.

## Env vars (Backend/.env — never commit)
- `DATABASE_URL` — Railway PostgreSQL
- `MONGO_URI` — Mongo Atlas (Tonder production read-replica)
- `DB_NAME`
- `SECRET_KEY` — JWT signing

## Domain rules (carry over from memory)

- **MongoDB deduplication is non-negotiable.** Every query that counts transactions MUST dedupe by `payment_id` (group + sort desc by `created` + take first). One `payment_id` = one user deposit intent; retries are not separate transactions. This applies to every report, every query, every consult — no exceptions.
- **Guardian + Tonder = one performance.** When measuring card success rate, treat `provider: tonder` + `provider: guardian` as one. Guardian is the anti-fraud layer, not a separate processor.
- **Filter on `acq`, not `provider`.** Cards combine `kushki` + `unlimit` → one rate. APMs: `bitso`, `stp`, `oxxopay`, `mercadopago`, `safetypay` → one rate each.
- **Status field is mixed case.** `status` contains both `"Success"` and `"SUCCESS"` — always `$toLower` it.
- **Withdrawals collection (`usrv-withdrawals-withdrawals`)**: amount is at `$monetary_amount.amount` (Decimal128), `business_id` is a **string** (vs number in transactions), no `business_name` field (join `business_business`).
- **Banregio taxonomy** — 12 movement types, CLABE-based detection. Full reference in `~/.claude/projects/-Users-yuyo/memory/truebook_banregio_labels.md`.
- Acceptance rate formula: `Success / (Success + Pending + Expired + Failed + Declined)`.

## Conventions
- Spanish in UI copy; English in code.
- Don't commit `.env*`, `Front/dist/`, `node_modules/`, `__pycache__/`, `.venv/`.
- Prisma schema lives only in `apps/web/prisma/` — doesn't affect the Python backend.
- Before running destructive SQL/Mongo queries, confirm the env target (Atlas production vs. local).

# Phase 5B Step 1: Cloud Deployment Preparation Plan

**Product:** AgentReliability AI  
**Role:** Senior DevOps Engineer, Cloud Architect, & SaaS Security Engineer  
**Date:** October 18, 2026  
**Status:** **READY FOR PROVISIONING (Awaiting Founder Approval)**  

---

## 1. Phase 5A Readiness Gate Verdict

Before designing or executing any cloud deployment preparations, we audited [`PHASE5A_STEP7_VERIFICATION.md`](file:///Users/aaryagopale/Desktop/AgentReliability/PHASE5A_STEP7_VERIFICATION.md).

### Gate Check Results
- **Critical End-to-End Workflows:** **PASSED** (all 16/16 user journey steps verified with real database execution).
- **Cross-Tenant Isolation:** **PASSED** (strict `404 Not Found` anti-enumeration verified across all resources).
- **Authentication & Authorization:** **PASSED** (scrypt hashing, server-side session tokens, double-submit CSRF).
- **API Key Revocation:** **PASSED** (immediate `401 Unauthorized` cutoff upon key deletion).
- **SDK & Offline CLI Compatibility:** **PASSED** (100% backward compatible without network dependencies).
- **Security Vulnerability Findings:** **0 Critical, 0 High**.

**GATE VERDICT:** **PASSED — SYSTEM IS CERTIFIED READY FOR CLOUD DEPLOYMENT PREPARATION.**

---

## 2. Recommended Cloud Architecture

To build a high-reliability, low-latency, and cost-efficient global SaaS, we recommend a modern decoupled cloud architecture:

```
                  ┌────────────────────────────────────────┐
                  │          Users / Web Browsers          │
                  └───────────────────┬────────────────────┘
                                      │
                         HTTPS (Custom Domain)
                                      │
                 ┌────────────────────┴────────────────────┐
                 ▼                                         ▼
   ┌───────────────────────────┐             ┌───────────────────────────┐
   │     Frontend (Vercel)     │             │   Backend API (Render)    │
   │  app.agentreliability.com │             │  api.agentreliability.com │
   │   - React 19 + Vite SPA   │             │   - FastAPI + Uvicorn     │
   │   - Global Edge CDN       │             │   - Health / Readiness    │
   │   - Zero-Downtime Deploys │             │   - Double-Submit CSRF    │
   └───────────────────────────┘             └─────────────┬─────────────┘
                                                           │
                                             Internal TLS Connection
                                                           │
                                                           ▼
                                             ┌───────────────────────────┐
                                             │ Managed Postgres (Neon)   │
                                             │   - Serverless Auto-Scale │
                                             │   - Automated Daily Backups│
                                             │   - Connection Pooling    │
                                             └───────────────────────────┘
```

### Component Architecture Breakdown
1. **Frontend Hosting — Vercel:**
   - Hosts our compiled React + Vite + Tailwind client bundle.
   - Deploys automatically on GitHub main branch pushes with instant preview deployments for PRs.
   - Global Edge CDN ensures fast page loads (<100ms) anywhere in the world.
   - Custom domain: `app.agentreliability.com`.

2. **Backend API Hosting — Render (Starter Plan) or Railway:**
   - Runs our FastAPI Python application using Uvicorn with `--proxy-headers`.
   - Continuous deployment directly from the repository.
   - Built-in zero-downtime rolling deploys and health-check monitoring via `/api/health`.
   - Custom domain: `api.agentreliability.com`.

3. **Production Database — Managed PostgreSQL (Neon / Render Postgres):**
   - Eliminates SQLite concurrency constraints for high-scale agent event streaming.
   - Neon serverless compute sleeps during zero-traffic hours and scales instantly during heavy test replay workloads.
   - Native automated point-in-time recovery (PITR) backups.

4. **Transactional Email Service — Resend:**
   - Dedicated REST API and Python SDK for delivering password reset emails, invite tokens, and alerts.
   - High deliverability with DKIM/SPF domain verification.

5. **DNS & Edge Defense — Cloudflare Free Tier:**
   - DNS management, automatic Let's Encrypt TLS certificates, DDoS mitigation, and HTTP/3 support.

---

## 3. Expected Costs & Free-Tier Limitations Comparison

We evaluated multiple hosting tiers to keep initial costs near zero while preventing production disruptions:

| Service | Option | Free Tier Allowance | Paid Tier (When Scaling) | Recommendation |
| :--- | :--- | :--- | :--- | :--- |
| **Frontend** | **Vercel** | 100 GB bandwidth/mo, unlimited preview deploys | Pro: \$20/user/mo (1 TB bandwidth) | **Recommended (Free)**: Ample capacity for early stage. |
| | Cloudflare Pages | Unlimited bandwidth, 500 builds/mo | \$20/mo | Viable alternative if bandwidth spikes. |
| **Backend API** | **Render** | Free tier has **50s cold starts** (unsuitable for API streaming) | **Starter Plan: \$7/mo** (0.5 CPU, 512 MB RAM, 24/7 online) | **Recommended (Starter \$7/mo)**: Prevents agent SDK timeout failures. |
| | Railway | \$5 one-time credit, then usage-based | ~$5–\$10/mo depending on RAM/CPU hours | Excellent alternative with built-in Postgres. |
| | Fly.io | 3 shared micro VMs | ~$5–\$8/mo + \$2/mo per dedicated IPv4 | Steeper operational learning curve. |
| **Database** | **Neon Postgres** | 0.5 GB storage, serverless autosuspend | Launch Plan: \$19/mo (10 GB storage) | **Recommended (Free)**: Zero cost to start, full Postgres. |
| | Render Postgres | 30-day free trial only | \$7/mo (1 GB RAM, 256 MB cache) | Good for co-located private network. |
| **Email** | **Resend** | 3,000 emails/mo (100 emails/day), 1 custom domain | \$20/mo (50,000 emails/mo) | **Recommended (Free)**: Ample for password resets. |
| **Domain** | Cloudflare / Namecheap | N/A | \$10–\$15 / year (`.com` / `.ai`) | Essential for branding and HTTPS cookies. |

### Total Initial Operating Cost
- **Launch Phase (Development / Beta):** **\$7.00 / month** (Render Starter backend to eliminate cold starts, everything else on generous free tiers).
- **100% Free Option:** Can start at **\$0.00 / month** on Railway trial or Render Free if 50-second initial wake-up times are acceptable during testing.

---

## 4. Files Created or Modified in Phase 5B Step 1

| File | Change Type | Purpose |
| :--- | :---: | :--- |
| [`backend/app/main.py`](file:///Users/aaryagopale/Desktop/AgentReliability/backend/app/main.py) | **Modified** | Added dynamic multi-environment CORS (`AGENTRELIABILITY_ALLOWED_ORIGINS`) and database-aware readiness checks on `/api/health`. |
| [`backend/app/security.py`](file:///Users/aaryagopale/Desktop/AgentReliability/backend/app/security.py) | **Modified** | Automatically defaults `COOKIE_SECURE=True` when `AGENTRELIABILITY_ENV=production`. |
| [`frontend/src/api.js`](file:///Users/aaryagopale/Desktop/AgentReliability/frontend/src/api.js) | **Modified** | Added support for configurable `VITE_API_BASE_URL` with transparent fallback to local Vite proxy. |
| [`backend/scripts/migrate_sqlite_to_postgres.py`](file:///Users/aaryagopale/Desktop/AgentReliability/backend/scripts/migrate_sqlite_to_postgres.py) | **Created** | Automated, zero-data-loss SQLite to PostgreSQL audit, schema generation, and data export tool. |
| [`backend/tests/test_postgres_migration_plan.py`](file:///Users/aaryagopale/Desktop/AgentReliability/backend/tests/test_postgres_migration_plan.py) | **Created** | Unit test verifying migration integrity, sequence updates, and foreign key corruption detection. |
| [`backend/.env.example`](file:///Users/aaryagopale/Desktop/AgentReliability/backend/.env.example) | **Created** | Clean backend environment template without hardcoded secrets. |
| [`frontend/.env.example`](file:///Users/aaryagopale/Desktop/AgentReliability/frontend/.env.example) | **Created** | Clean frontend environment template. |
| [`vercel.json`](file:///Users/aaryagopale/Desktop/AgentReliability/vercel.json) | **Created** | Vercel production build, single-page app rewrite configuration, and HTTP security headers. |
| [`render.yaml`](file:///Users/aaryagopale/Desktop/AgentReliability/render.yaml) | **Created** | Render Blueprint for zero-downtime FastAPI service deployment. |

---

## 5. Required Production Environment Variables

### Backend Environment Variables (Configured in Render/Railway Dashboard)
```bash
# Environment Mode
AGENTRELIABILITY_ENV=production

# Server Port (injected automatically by PaaS)
PORT=8001

# Database Connection (Neon or Render Postgres connection string)
DATABASE_URL=postgresql://user:password@ep-cool-fog-123456.us-east-2.aws.neon.tech/agentreliability?sslmode=require

# Trusted CORS Origins (frontend domain)
AGENTRELIABILITY_ALLOWED_ORIGINS=https://app.agentreliability.com

# Cookie Security
AGENTRELIABILITY_COOKIE_SECURE=true
AGENTRELIABILITY_COOKIE_SAMESITE=lax
AGENTRELIABILITY_SESSION_MAX_AGE_SECONDS=604800

# Rate Limiting
AGENTRELIABILITY_RATE_LIMIT_MAX=5
AGENTRELIABILITY_RATE_LIMIT_WINDOW=900

# Transactional Email (Optional for launch, required for public password resets)
RESEND_API_KEY=re_your_api_key_here
EMAIL_FROM=noreply@agentreliability.com
```

### Frontend Environment Variables (Configured in Vercel Dashboard)
```bash
# Backend API Base URL
VITE_API_BASE_URL=https://api.agentreliability.com
```

---

## 6. Database Migration Plan (SQLite $\rightarrow$ PostgreSQL)

Our migration strategy guarantees **100% data preservation and referential integrity**:

### Migration Execution Procedure
1. **Safety Backup:**
   Before migrating, copy `backend/agentreliability.db` to `backend/agentreliability.db.pre_postgres.bak`.
2. **Pre-Flight Integrity Check:**
   Run the migration audit tool:
   ```bash
   python backend/scripts/migrate_sqlite_to_postgres.py --source-db backend/agentreliability.db --dry-run
   ```
   *Verified dry-run output:* `Referential Integrity: [PASS] No violations`.
3. **Data Dump Generation:**
   Generate the PostgreSQL-compliant SQL script:
   ```bash
   python backend/scripts/migrate_sqlite_to_postgres.py --source-db backend/agentreliability.db --output-sql /tmp/postgres_migration.sql
   ```
4. **Target Ingestion:**
   Load into the target Postgres database:
   ```bash
   psql "$DATABASE_URL" -f /tmp/postgres_migration.sql
   ```
5. **Sequence Synchronization:**
   The script automatically executes `SELECT setval(pg_get_serial_sequence('<table>', 'id'), ...)` for all tables so new records generated in Postgres never collide with migrated IDs.
6. **Rollback Strategy:**
   If any error occurs during migration, the migration runs inside a single Postgres transaction (`BEGIN; ... COMMIT;`), ensuring automatic atomic rollback. Local SQLite data remains untouched throughout.

---

## 7. Security Considerations

1. **No Secrets in Source Control:**
   Neither API keys, passwords, database passwords, nor session secrets are committed to Git. `.env.example` templates document every variable with safe dummy placeholders.
2. **Production Fail-Closed Email Sink:**
   `email_sink.py` and `auth_api.py` are strictly configured so `dev_reset_token` is never returned in API responses or logs when `AGENTRELIABILITY_ENV=production`.
3. **Strict Transport Security (HTTPS):**
   `COOKIE_SECURE=True` ensures all session and CSRF cookies are transmitted strictly over TLS.
4. **Reverse Proxy Header Trust:**
   Backend runs with `--proxy-headers` so client IP addresses for rate limiting and audit logs are accurately resolved from `X-Forwarded-For`.
5. **Anti-Enumeration Maintained:**
   All 404 anti-enumeration protections from Phase 5A remain active in the production code.

---

## 8. Verification & Test Results

All verification suites were executed locally in isolated sandboxes:

```
==================== BACKEND TEST SUITE ====================
backend/tests/test_api.py ......................... PASSED
backend/tests/test_auth_api.py .................... PASSED
backend/tests/test_authorization.py ............... PASSED
backend/tests/test_ci_api.py ...................... PASSED
backend/tests/test_detector.py .................... PASSED
backend/tests/test_e2e_journey.py ................. PASSED
backend/tests/test_frontend_auth_integration.py ... PASSED
backend/tests/test_migrations.py .................. PASSED
backend/tests/test_postgres_migration_plan.py ..... PASSED
backend/tests/test_projects_api.py ................ PASSED
backend/tests/test_replay.py ...................... PASSED
backend/tests/test_security.py .................... PASSED
backend/tests/test_tests_api.py ................... PASSED
backend/tests/test_traces.py ...................... PASSED
Result: 104 passed in 3.03s (0 failed)

====================== SDK TEST SUITE ======================
sdk/tests/test_cli.py ............................. PASSED
sdk/tests/test_sdk.py ............................. PASSED
Result: 33 passed in 0.35s (0 failed)

=================== FRONTEND PRODUCTION BUILD ===================
vite build completed in 358ms
dist/index.html                   0.43 kB
dist/assets/index-d6w0RDz5.js   301.98 kB (gzip: 86.18 kB)
dist/assets/index-y4kQdW-d.css   30.27 kB (gzip:  5.92 kB)
Result: SUCCESS (0 errors, 0 warnings)

=================== PORT ISOLATION CHECK ===================
Port 8000: CropBazaar Python (PIDs 5637, 24581) -> UNTOUCHED
Port 8001: AgentReliability Backend (PIDs 96728, 6386) -> ACTIVE
Port 5174: AgentReliability Frontend (PID 84244) -> ACTIVE
```

---

## 9. Step-by-Step Deployment Instructions (When Ready)

Once you approve deployment to production, follow these straightforward steps:

### Step A: Database Provisioning (5 minutes)
1. Sign up at [Neon.tech](https://neon.tech) (Free).
2. Create a project named `agentreliability`.
3. Copy the Postgres connection string: `postgresql://...`.
4. Run the data migration script to import historical data:
   ```bash
   python backend/scripts/migrate_sqlite_to_postgres.py --source-db backend/agentreliability.db --output-sql migration.sql
   psql "<NEON_CONNECTION_STRING>" -f migration.sql
   ```

### Step B: Backend Deployment on Render (5 minutes)
1. Sign up at [Render.com](https://render.com).
2. Connect your GitHub repository: `aaryagopale-ui/AgentReliability`.
3. Create a **New Web Service** using the Starter Plan (\$7/mo).
4. Set:
   - **Root Directory:** `.`
   - **Build Command:** `pip install -r backend/requirements.txt`
   - **Start Command:** `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers`
   - **Health Check Path:** `/api/health`
5. Add the environment variables from Section 5.

### Step C: Frontend Deployment on Vercel (3 minutes)
1. Sign up at [Vercel.com](https://vercel.com).
2. Import repository `aaryagopale-ui/AgentReliability`.
3. Set **Framework Preset:** `Vite`.
4. Set **Root Directory:** `frontend`.
5. Add Environment Variable:
   - `VITE_API_BASE_URL` = `https://<YOUR_RENDER_BACKEND_URL>.onrender.com`
6. Click **Deploy**.

---

## 10. Remaining Blockers / Decisions for Founder

No technical blockers exist. The following decisions are ready for your review:
1. **Approval of Architecture:** Confirm whether the Vercel (Frontend) + Render (FastAPI Backend) + Neon (Serverless Postgres) stack meets your cost and scaling expectations.
2. **Custom Domain:** Decide whether to deploy initially on default provider subdomains (`*.vercel.app` and `*.onrender.com`) for free, or connect a custom domain (`agentreliability.com`).
3. **Commit & Push Authorization:** Per your standing instructions, **no files have been committed or pushed to GitHub, and no cloud accounts or resources have been created**.

---

*Report prepared and certified by Senior DevOps & Cloud Architecture Lead.*


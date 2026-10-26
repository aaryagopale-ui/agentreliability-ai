# AgentReliability AI — MVP Remaining Tasks & Roadmap

**Date:** October 19, 2026  
**Auditor:** Senior Infrastructure Engineer, Security Architect & Developer Experience Lead  
**Status:** MVP core capabilities complete and verified.

---

## 1. Post-MVP Recommended Enhancements (Prioritized)

### Priority 1: Framework Package Extras & Environment Bundling
- [ ] **CrewAI Package Support:** Add `crewai` to optional extras (`pip install 'agentreliability[crewai]'`) once dependency resolver compatibility with the active environment's Python version is resolved.
- [ ] **Native Framework Auto-Instrumentation:** Provide a single-line CLI wrapper (e.g. `agentreliability run python my_agent.py`) that automatically hooks supported frameworks without requiring explicit callback handler code.

### Priority 2: Enterprise Observability & Alerts
- [ ] **Email & Webhook Notifications:** Expand `backend/app/email_sink.py` to support real SMTP / Resend and outbound webhook alerts (Slack, Discord, PagerDuty) on breaking regression or elevated failure rate.
- [ ] **SLO & Error Budget Tracking:** Add project-level SLO definitions (e.g. 99% success rate, <500ms p95 latency) with visual burn-down charts on the Overview page.

### Priority 3: Advanced Failure Intelligence
- [ ] **Hosted LLM Fallback:** Allow configuring optional cloud LLM providers (e.g. OpenAI, Anthropic, Gemini API keys stored project-side) when local Ollama is offline or insufficient.
- [ ] **Semantic Output Distance:** Add optional embedding similarity checks for natural language agent responses (cosine similarity threshold) to complement exact and structured JSON output matching.

### Priority 4: Production Deployment & Multi-Region Cloud
- [ ] **Managed PostgreSQL Migration:** Execute automated schema migrations against managed PostgreSQL (AWS RDS / Supabase / Neon) following the tested staging plan in `PHASE5B_STEP3_STAGING_REPORT.md`.
- [ ] **Distributed Task Queue:** Replace background thread queue with Redis / Celery or BullMQ for high-throughput ingestion (>10,000 spans/sec).

---

## 2. Immediate Operational Checklist for Developers

1. **Local Development:**
   - Backend running at `http://127.0.0.1:8001` via `backend/.venv/bin/uvicorn app.main:app --port 8001 --reload`
   - Frontend running at `http://127.0.0.1:5174` via `npm run dev` in `frontend/`
2. **Project Validation:**
   - Active MVP Validation project: `MVP Order Processing Validation` (ID: 150)
   - Sample agent implementation: `examples/mvp_validation/order_agent.py`
   - End-to-end scenario test: `examples/mvp_validation/test_mvp_scenarios.py`
3. **CI/CD Integration:**
   - Workflow file: `.github/workflows/agent-tests.yml`
   - CLI command: `agentreliability test --project ./agent-tests --output results.json --baseline baseline.json`


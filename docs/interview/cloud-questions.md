# Cloud / Deployment Questions

**Important context for these answers:** nothing described below as a cloud
target is actually deployed. This project runs as local dev processes only
(see [deployment-architecture.md](../architecture/deployment-architecture.md)).
These answers describe what I'd do to get it there, not what exists.

**Q: Is this deployed anywhere?**
No. It runs locally: Django's dev server, a local or single-container
Postgres, and the Vite dev server. `docker-compose.yml` only provisions
Postgres for local convenience — it's explicitly commented as "not a
deployment topology."

**Q: How would you actually deploy this?**
Backend behind gunicorn/uvicorn + a reverse proxy (nginx or a managed load
balancer); Postgres on a managed service (RDS or equivalent) instead of a
local container; the FAISS index replaced by pgvector so multiple backend
instances share one consistent vector store instead of each holding its own
in-memory copy (see [ADR-0004](../decisions/0004-faiss-vector-store.md));
the frontend built (`npm run build`) and served as static assets from a CDN
or static host, pointed at the real backend origin via
`VITE_API_BASE_URL`; secrets moved from `.env` to the platform's secrets
manager.

**Q: What's the biggest architectural blocker to deploying this as-is?**
The FAISS index. It's an in-process, in-memory structure with a
file-on-disk backing — running two backend instances behind a load balancer
today would give each one its own separately-loaded copy of the index, with
writes from one instance invisible to the other until a restart. Everything
else (Django, Postgres, the frontend) is stateless-per-request and would
scale horizontally without changes.

**Q: How would ingestion change under real traffic?**
Right now embedding + indexing happens synchronously inside the upload
request. Under real traffic (or just larger documents), that should move to
a background job (Celery + Redis, or a managed queue) with the upload
endpoint returning immediately and the `Document.status` field (already
modeled as `ready`/`failed`) gaining a `processing` state the frontend can
poll or the UI can reflect via a status endpoint. This isn't built — it's
the first thing I'd add if upload latency or request timeouts became a real
problem.

**Q: What would you monitor in production?**
LLM call latency and failure rate by exception type (rate limit vs. auth vs.
network vs. refusal — `rag/services/llm.py` already logs the real exception
server-side, so this is a matter of routing that log to a metrics/alerting
pipeline, not restructuring the code); FAISS index size and search latency,
since both degrade as the index grows past what a flat index handles well;
ingestion failure rate by `Document.status`, since a spike in `failed`
documents is a direct, queryable signal already sitting in Postgres.

**Q: What's the honest gap between "this repo" and "production-ready"?**
No auth, no multi-tenancy, no background job queue, no observability beyond
one error log line, a vector store that doesn't survive horizontal scaling,
and no deployment pipeline of any kind. This is a demonstrable, coherent
MVP of the *pipeline* — not infrastructure that's been hardened for
production traffic.

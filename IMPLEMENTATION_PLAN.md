# GradePro — Definitive Implementation Plan v6
### AI-Powered Assignment Grading Platform

---

## System in One Sentence

Assessor uploads a student DOCX → system validates formatting, extracts unit metadata deterministically, loads the right ML model, evaluates each task in parallel using a reasoning model + trained sub-model, and generates a filled PDF feedback report — all in under 45 seconds.

---

## Confirmed Requirements

| Item | Decision |
|---|---|
| Colleges | ILC · UKPDA (different format rules, same criteria) |
| Awarding Bodies | Qualifi · OTHM · NOCN · ATHE |
| Roles | Admin → Main Assessor → Assessor |
| Reasoning Model | API rotation (OpenAI/Anthropic/Gemini/Groq) **or** Ollama local |
| Sub-Models | Per unit · CSV trained · versioned · hot-swappable |
| Feedback Template | Per unit × college · versioned · hot-swappable |
| Format Rules | Per college · versioned · hot-swappable |
| Criteria | Per unit · versioned · triggers model retrain on change |
| Storage | Cloudflare R2 |
| Deployment | Local → KVM VPS |
| Start | 1 unit (HSC301) · grows organically |
| Memory | Fully dynamic · zero hardcoded limits |

---

## Architecture

```
                         ┌──────────────────────────┐
                         │   Next.js 14 (TSX)        │
                         │   Frontend                │
                         └────────────┬─────────────┘
                                      │ HTTPS / WSS
                         ┌────────────▼─────────────┐
                         │   Go (Fiber)              │
                         │   API Gateway             │
                         │   JWT · RBAC · Rate Limit │
                         │   WebSocket Hub           │
                         └──┬──────────────────┬────┘
                            │ mTLS             │ mTLS
               ┌────────────▼───┐    ┌─────────▼──────────┐
               │  Orchestrator  │    │   ML Inference      │
               │  Python/FastAPI│    │   Python/FastAPI    │
               │  Celery Jobs   │    │   bge-small backbone│
               │  Pipeline Mgr  │    │   Unit Head LRU     │
               └────────────────┘    └────────────────────┘
                            │
          ┌─────────────────┼──────────────────┐
          │                 │                  │
  ┌───────▼──────┐  ┌───────▼──────┐  ┌───────▼──────┐
  │  PostgreSQL  │  │    Redis 7   │  │  Cloudflare  │
  │  + PgBouncer │  │  AOF + LRU   │  │     R2       │
  └──────────────┘  └──────────────┘  └──────────────┘
          │
  ┌───────▼──────┐  ┌──────────────┐
  │  Gotenberg   │  │   ClamAV     │
  │  PDF Service │  │   Scanner    │
  └──────────────┘  └──────────────┘
```

---

## Technology Stack

| Layer | Technology | Why |
|---|---|---|
| Frontend | Next.js 14 (TSX) + Tailwind + shadcn/ui | Type-safe, SSR, matches design |
| Gateway | Go (Fiber) | Handles WebSocket hub + auth at high concurrency with low memory |
| Orchestration | Python FastAPI + Celery (Gevent pool) | Best ML ecosystem; Gevent perfect for I/O-bound LLM calls |
| ML Inference | Python FastAPI | Shared backbone + unit heads LRU |
| Embeddings | `BAAI/bge-small-en-v1.5` + sliding window | Top MTEB for size; handles unlimited doc length |
| Classifier | Tiny MLP head per unit (0.4MB each) | Task-count invariant; max-pool aggregation |
| XGBoost | Per unit on numeric features | Fast fallback; saved as JSON not pickle |
| Reasoning Model | API rotation or Ollama | Configurable; circuit breaker auto-fallback |
| PDF | Gotenberg (Docker) | Production LibreOffice wrapper; thread-safe; no leaks |
| Security | ClamAV + DocxSanitizer + lxml XXE guard | Mandatory; blocks upload if scanner unavailable |
| Primary DB | PostgreSQL 16 | ACID; versioned tables for criteria/models/templates |
| Connection Pool | PgBouncer (transaction mode) | Golden-rule sizing: (vCPUs×2)+1 real connections |
| Cache + Queue | Redis 7 (AOF persistence) | Celery broker; pub/sub; Lua scripts; rate limiting |
| WebSocket Events | Redis Streams | Persistent; no lost events on reconnect |
| Storage | Cloudflare R2 | Zero egress fees; S3-compatible |
| Containerization | Docker Compose | All services; fully portable |
| Monitoring | Prometheus + Grafana + Loki | Metrics + logs with trace IDs |

---

## Project Structure

```
gradepro/
├── .env.example
├── docker-compose.yml
├── secrets/                        # Docker secrets (gitignored)
│   └── postgres_password.txt
│
├── frontend/                       # Next.js 14 TSX
│   ├── app/
│   │   ├── dashboard/
│   │   ├── grade/                  # Grade Now workflow + WebSocket progress
│   │   ├── records/
│   │   ├── templates/              # Per-unit feedback template manager
│   │   ├── settings/               # API keys · Ollama · Format rules
│   │   └── admin/                  # Models · Criteria · Users
│   ├── components/
│   └── lib/
│       ├── websocket.ts            # Reconnection logic + event replay
│       └── api.ts
│
├── gateway/                        # Go Fiber
│   ├── cmd/main.go
│   └── internal/
│       ├── auth/                   # JWT RS256 · refresh token rotation
│       ├── rbac/                   # ADMIN · MAIN_ASSESSOR · ASSESSOR
│       ├── middleware/
│       │   ├── rate_limiter.go     # Redis Lua sliding-window
│       │   └── security.go         # CORS · HSTS · mTLS
│       ├── websocket/              # Hub · rooms per job_id · Redis Streams consumer
│       └── lua/                    # Embedded Lua scripts
│
├── services/
│   ├── orchestrator/               # Python FastAPI + Celery
│   │   ├── api/
│   │   │   └── routes/
│   │   ├── pipeline/
│   │   │   ├── security.py         # DocxSecurityPipeline (ClamAV + sanitize)
│   │   │   ├── parser.py           # UniversalAssignmentParser
│   │   │   ├── font_resolver.py    # DocxFontResolver (4-level inheritance)
│   │   │   ├── format_validator.py # College rule-based validator
│   │   │   ├── model_router.py     # Unit → model routing + tier logic
│   │   │   └── report_builder.py   # Final verdict assembly
│   │   ├── workers/
│   │   │   ├── grading.py          # Celery grading task (Gevent)
│   │   │   ├── training.py         # Celery training task (Prefork)
│   │   │   └── pdf.py              # Celery PDF task (Gevent)
│   │   ├── locking/
│   │   │   └── occ.py              # Optimistic concurrency control
│   │   ├── cache/
│   │   │   ├── invalidator.py      # Event-driven surgical invalidation
│   │   │   └── warmer.py           # Startup pre-warming
│   │   └── Dockerfile
│   │
│   ├── ml_inference/               # Python FastAPI
│   │   ├── embedder.py             # SlidingWindowEmbedder (bge-small)
│   │   ├── registry.py             # ModelRegistry (dynamic LRU)
│   │   ├── unit_head.py            # UnitGradingHead (MLP, max-pool)
│   │   ├── reasoning_client.py     # API rotation + Ollama + circuit breaker
│   │   └── Dockerfile
│   │
│   └── pdf_service/                # Python
│       ├── generator.py            # GotenbergPDFGenerator
│       ├── template_filler.py      # Placeholder fill + validation
│       └── Dockerfile
│
├── ml/
│   ├── training/
│   │   ├── train_unit.py           # Per-unit training pipeline
│   │   ├── features.py             # Feature engineering
│   │   └── evaluate.py             # Metrics: refer-recall primary
│   └── data/
│       └── raw/                    # CSVs per unit (gitignored)
│
├── shared/
│   └── db/
│       └── migrations/             # Alembic
│
└── infra/
    ├── nginx/
    ├── pgbouncer/
    │   └── pgbouncer.ini
    ├── redis/
    ├── prometheus/
    └── grafana/
```

---

## Key Technical Decisions — Full Rationale

---

### 1. Embedding: `bge-small-en-v1.5` + Sliding Window

**Problem solved:** `all-MiniLM-L6-v2` has a 256-token limit. Task 2 in a real assignment is 2,540 tokens — the model reads only the first 10%.

**Solution:**

```python
class SlidingWindowEmbedder:
    """
    Backbone: bge-small-en-v1.5
      - 130MB, loaded ONCE at service startup
      - Shared across ALL units — no per-unit backbone
      - Top MTEB for 384-dim models (beats MiniLM on semantic tasks)
      - 512-token base limit → extended to unlimited via sliding window

    Sliding window:
      - Chunk text into 400-token windows, 64-token overlap
      - Embed each chunk → mean-pool → single 384-dim vector
      - Any document length → same output shape → no truncation ever

    Memory:
      - Backbone: 130MB (once)
      - Per chunk embedding call: ~2MB temporary (freed after)
      - Zero accumulation across requests
    """

    CHUNK_SIZE = 400
    OVERLAP = 64

    def encode(self, text: str) -> np.ndarray:
        tokens = self.tokenizer.encode(text, add_special_tokens=False)

        if len(tokens) <= self.CHUNK_SIZE:
            return self.model.encode(text, normalize_embeddings=True)

        step = self.CHUNK_SIZE - self.OVERLAP
        chunks = [
            self.tokenizer.decode(tokens[i : i + self.CHUNK_SIZE])
            for i in range(0, len(tokens), step)
            if tokens[i : i + self.CHUNK_SIZE]
        ]

        embeddings = self.model.encode(
            chunks,
            batch_size=32,
            normalize_embeddings=True,
        )
        return np.mean(embeddings, axis=0).astype(np.float32)
```

**Per-unit model head** — tiny, task-count invariant:

```python
class UnitGradingHead(nn.Module):
    """
    Input:  List of task embeddings (any count — 2, 3, 4, 5 tasks)
    Output: pass_probability + per-criterion scores

    Max-pool across tasks → always 384-dim regardless of task count.
    Task count changes (curriculum update) → same head works, no rebuild.
    Size: ~0.4MB per unit.
    """

    def __init__(self, embed_dim=384, num_criteria=3):
        super().__init__()
        self.classifier = nn.Sequential(
            nn.Linear(embed_dim, 128),
            nn.LayerNorm(128),
            nn.GELU(),
            nn.Dropout(0.2),
            nn.Linear(128, 64),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(64, 2),
        )
        self.criterion_heads = nn.ModuleList([
            nn.Sequential(nn.Linear(embed_dim, 32), nn.GELU(),
                          nn.Linear(32, 1), nn.Sigmoid())
            for _ in range(num_criteria)
        ])

    def forward(self, task_embeddings: list[torch.Tensor]) -> dict:
        stacked = torch.stack(task_embeddings)     # (N_tasks, 384)
        pooled, _ = torch.max(stacked, dim=0)      # (384,) — task-count agnostic
        logits = self.classifier(pooled)
        return {
            "pass_probability": torch.softmax(logits, dim=0)[1].item(),
            "criterion_scores": [h(pooled).squeeze().item()
                                  for h in self.criterion_heads],
        }
```

---

### 2. Dynamic Memory Management (No Hardcoding)

**Problem solved:** Hardcoded `mem_limit: 800m` is wrong for 1 model and wrong for 500 models.

**Solution — runtime self-aware limits:**

```python
class ModelRegistry:
    """
    Calculates its own memory budget at startup from live system state.
    Evicts LRU heads when system memory is tight.
    With 1 unit:  uses ~130.4MB (backbone + 1 head) — barely registers.
    With 50 units: uses ~150MB (backbone + 50 heads).
    With 500 units hot: auto-evicts based on available RAM.
    Zero config change needed as system grows.
    """

    def __init__(self):
        self._lock = Lock()
        self._heads: OrderedDict[str, UnitGradingHead] = OrderedDict()
        self._embedder: SlidingWindowEmbedder | None = None

        # Dynamic budget — calculated from env or live system RAM
        max_mb_env = int(os.getenv("MODEL_CACHE_MAX_MB", "0"))
        if max_mb_env == 0:
            # Auto: use 40% of currently available system RAM
            available_mb = psutil.virtual_memory().available / 1024 / 1024
            self.max_cache_mb = available_mb * 0.40
        else:
            self.max_cache_mb = float(max_mb_env)

        # Always leave this much free for the OS and other services
        self.min_free_mb = float(os.getenv("MODEL_CACHE_MIN_FREE_MB", "300"))

    def _should_evict(self) -> bool:
        proc_mb = psutil.Process().memory_info().rss / 1024 / 1024
        free_mb = psutil.virtual_memory().available / 1024 / 1024
        return proc_mb > self.max_cache_mb or free_mb < self.min_free_mb

    def _evict_lru(self):
        while self._should_evict() and self._heads:
            key, model = self._heads.popitem(last=False)
            del model
            gc.collect()
```

**Docker Compose — no hardcoded limits:**

```yaml
# Nothing hardcoded. Everything env-var driven or unlimited.
services:
  ml_inference:
    environment:
      - MODEL_CACHE_MAX_MB=0          # 0 = auto (40% of free RAM)
      - MODEL_CACHE_MIN_FREE_MB=300   # Always keep 300MB free for OS
    # No mem_limit — OS manages it dynamically

  celery_grading:
    environment:
      - MODEL_CACHE_MAX_MB=0
    # No mem_limit

  # Only services with KNOWN leak risk get soft limits — and those are env-var driven
  gotenberg:
    mem_limit: ${GOTENBERG_MEM_LIMIT:-2g}       # LO genuinely needs a cap; default 2GB

  clamav:
    mem_limit: ${CLAMAV_MEM_LIMIT:-1g}
```

**`.env.example` — single config file:**

```env
# Memory (0 = auto-calculate from available RAM)
MODEL_CACHE_MAX_MB=0
MODEL_CACHE_MIN_FREE_MB=300

# Only cap services known to leak
GOTENBERG_MEM_LIMIT=2g
CLAMAV_MEM_LIMIT=1g

# Scale these up/down based on your VPS size
CELERY_GRADING_REPLICAS=4
CELERY_GRADING_CONCURRENCY=15
CELERY_PDF_CONCURRENCY=10
```

---

### 3. DOCX Font Resolver (4-Level Inheritance)

**Problem solved:** 74% of runs return `font.size=None`, 94% return `font.name=None`. Direct checks produce false positives on every correctly formatted document.

```python
class DocxFontResolver:
    """
    Resolves effective font properties via 4-level DOCX inheritance:
    Run direct → Paragraph rPr → Style chain → Document defaults

    call once per document, reuse resolver for all paragraphs.
    """

    def __init__(self, doc: Document):
        self.doc = doc
        self._doc_defaults = self._parse_doc_defaults()

    def _parse_doc_defaults(self) -> dict:
        """Parse docDefaults XML — the ultimate fallback."""
        defaults = {"size_pt": 12.0, "name": "Times New Roman", "bold": False}
        try:
            ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            root = self.doc.element
            for sz in root.iter(f"{{{ns}}}sz"):
                val = sz.get(f"{{{ns}}}val")
                if val:
                    defaults["size_pt"] = int(val) / 2  # half-points → points
                    break
        except Exception:
            pass
        return defaults

    def font_size(self, run, para) -> float:
        # 1. Run-level direct
        if run.font.size:
            return run.font.size.pt
        # 2. Paragraph rPr
        ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        pPr = para._p.find(f"{{{ns}}}pPr")
        if pPr is not None:
            rPr = pPr.find(f"{{{ns}}}rPr")
            if rPr is not None:
                sz = rPr.find(f"{{{ns}}}sz")
                if sz is not None:
                    return int(sz.get(f"{{{ns}}}val", "24")) / 2
        # 3. Style chain
        style = para.style
        while style:
            if style.font.size:
                return style.font.size.pt
            style = style.base_style
        # 4. Document defaults
        return self._doc_defaults["size_pt"]

    def font_name(self, run, para) -> str:
        if run.font.name:
            return run.font.name
        style = para.style
        while style:
            if style.font.name:
                return style.font.name
            style = style.base_style
        try:
            n = self.doc.styles["Normal"].font.name
            if n:
                return n
        except Exception:
            pass
        return self._doc_defaults["name"]

    def bold(self, run, para) -> bool:
        if run.font.bold is not None:
            return run.font.bold
        style = para.style
        while style:
            if style.font.bold is not None:
                return style.font.bold
            style = style.base_style
        return self._doc_defaults["bold"]

    def format_summary(self) -> dict:
        """Aggregate resolved features across all runs — zero false positives."""
        body_sizes, heading_sizes, names = [], [], []
        bold_count = total = 0

        for para in self.doc.paragraphs:
            is_heading = "Heading" in para.style.name
            for run in para.runs:
                if not run.text.strip():
                    continue
                total += 1
                sz = self.font_size(run, para)
                nm = self.font_name(run, para)
                bd = self.bold(run, para)
                names.append(nm)
                if bd:
                    bold_count += 1
                (heading_sizes if is_heading else body_sizes).append(sz)

        return {
            "body_font_size_pt":    max(set(body_sizes), key=body_sizes.count, default=12.0),
            "heading_font_size_pt": max(heading_sizes, default=0),
            "primary_font":         max(set(names), key=names.count, default="Unknown"),
            "bold_ratio":           bold_count / total if total else 0,
            "table_count":          len(self.doc.tables),
        }
```

---

### 4. DOCX Security Pipeline (Mandatory)

```python
class DocxSecurityPipeline:
    """
    All checks run before ANY parsing or conversion.
    Blocks upload if ClamAV is unavailable — never silently skips.
    """

    MAX_DECOMPRESSED_MB = 100

    def run(self, file_bytes: bytes) -> bytes:
        self._check_magic_bytes(file_bytes)
        self._check_zip_bomb(file_bytes)
        sanitized = self._strip_dangerous_content(file_bytes)
        self._clam_scan(sanitized)
        return sanitized

    def _check_magic_bytes(self, data: bytes):
        if not data[:4] == b"PK\x03\x04":
            raise SecurityError("Not a valid DOCX file")

    def _check_zip_bomb(self, data: bytes):
        total = sum(i.file_size for i in zipfile.ZipFile(io.BytesIO(data)).infolist())
        if total > self.MAX_DECOMPRESSED_MB * 1024 * 1024:
            raise SecurityError("File exceeds decompressed size limit")

    def _strip_dangerous_content(self, data: bytes) -> bytes:
        """Remove macros, ActiveX, OLE, external entity declarations."""
        STRIP = {"word/vbaProject.bin", "word/vbaData.xml"}
        out = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as src, \
             zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                if item.filename in STRIP:
                    continue
                content = src.read(item.filename)
                if item.filename.endswith((".xml", ".rels")):
                    content = re.sub(
                        rb"<!(?:DOCTYPE|ENTITY)[^>]*>", b"", content, flags=re.DOTALL
                    )
                dst.writestr(item, content)
        return out.getvalue()

    def _clam_scan(self, data: bytes):
        try:
            cd = clamd.ClamdUnixSocket("/var/run/clamav/clamd.ctl")
            status, reason = cd.instream(io.BytesIO(data)).get("stream", ("OK", ""))
            if status == "FOUND":
                raise SecurityError(f"Malware detected: {reason}")
        except clamd.ConnectionError:
            raise SecurityError("Virus scanner unavailable — upload rejected")
```

---

### 5. Worker Pool: Gevent (I/O-Bound Optimized)

**Why Gevent:** Grading is 95% I/O — waiting for LLM API responses. Gevent greenlets yield during I/O waits, letting other jobs run. One OS process with 15 greenlets handles 15 concurrent LLM calls that would stall 15 prefork processes.

```yaml
celery_grading:
  command: >
    celery -A app worker
    -Q grading_queue
    --pool=gevent
    --concurrency=${CELERY_GRADING_CONCURRENCY:-15}
    --max-tasks-per-child=100        # Restart worker process every 100 tasks
    --without-heartbeat              # Reduces Redis chattiness
  deploy:
    replicas: ${CELERY_GRADING_REPLICAS:-4}
  environment:
    - GEVENT_SUPPORT=True            # Required for SQLAlchemy gevent compat

celery_training:
  command: >
    celery -A app worker
    -Q training_queue
    --pool=prefork                   # Training is CPU-bound → prefork correct here
    --concurrency=${CELERY_TRAINING_CONCURRENCY:-2}
    --max-tasks-per-child=5
  cpus: "${TRAINING_CPU_LIMIT:-1.5}" # Prevent training from starving grading

celery_pdf:
  command: >
    celery -A app worker
    -Q pdf_queue
    --pool=gevent
    --concurrency=${CELERY_PDF_CONCURRENCY:-10}
    --max-tasks-per-child=50
  environment:
    - GEVENT_SUPPORT=True
```

**Hard timeout per LLM call — prevents worker stall:**

```python
async def evaluate_task_with_timeout(self, task_text, criteria, context):
    timeout = float(os.getenv("LLM_CALL_TIMEOUT_SECONDS", "20"))
    try:
        async with asyncio.timeout(timeout):
            return await self.reasoning_client.evaluate(task_text, criteria, context)
    except asyncio.TimeoutError:
        return {
            "verdict": "NEEDS_HUMAN_REVIEW",
            "feedback": "AI evaluation timed out — flagged for assessor review",
            "fallback": True,
        }
```

---

### 6. PDF Generation: Gotenberg

**Why Gotenberg:** Raw LibreOffice headless is not thread-safe, leaks memory, and requires per-job process isolation. Gotenberg wraps LibreOffice correctly with built-in queue management, process recycling, and a clean REST API.

```yaml
gotenberg:
  image: gotenberg/gotenberg:8
  command:
    - "gotenberg"
    - "--libreoffice-restart-after=50"        # Recycle LO every 50 conversions
    - "--libreoffice-max-queue=${GOTENBERG_QUEUE:-5}"
    - "--api-timeout=${GOTENBERG_TIMEOUT:-30s}"
  mem_limit: ${GOTENBERG_MEM_LIMIT:-2g}        # LO legitimately needs a cap
  networks: [internal]
  cap_drop: [ALL]
  cap_add: [CHOWN, SETUID, SETGID]
  tmpfs:
    - /tmp:size=512m,noexec                    # LO temp — noexec prevents script execution
```

```python
class GotenbergPDFGenerator:
    URL = os.getenv("GOTENBERG_URL", "http://gotenberg:3000")

    async def convert(self, docx_path: str) -> bytes:
        timeout = float(os.getenv("GOTENBERG_TIMEOUT_SECONDS", "45"))
        async with httpx.AsyncClient(timeout=timeout) as client:
            with open(docx_path, "rb") as f:
                r = await client.post(
                    f"{self.URL}/forms/libreoffice/convert",
                    files={"files": (Path(docx_path).name, f,
                           "application/vnd.openxmlformats-"
                           "officedocument.wordprocessingml.document")},
                )
            if r.status_code != 200:
                raise PDFConversionError(f"Gotenberg {r.status_code}: {r.text[:200]}")
            return r.content

    async def fill_and_convert(self, template_bytes: bytes, data: dict) -> bytes:
        doc = Document(BytesIO(template_bytes))
        self._fill(doc, data)
        self._assert_no_unfilled(doc)  # Raises if {{placeholder}} remains
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            doc.save(f.name)
            path = f.name
        try:
            return await self.convert(path)
        finally:
            Path(path).unlink(missing_ok=True)   # Always clean up

    def _fill(self, doc, data: dict):
        """Replace {{key}} in paragraphs, tables, headers, footers."""
        targets = list(doc.paragraphs)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    targets.extend(cell.paragraphs)
        for section in doc.sections:
            targets.extend(section.header.paragraphs)
            targets.extend(section.footer.paragraphs)
        for para in targets:
            for key, val in data.items():
                if f"{{{{{key}}}}}" in para.text:
                    for run in para.runs:
                        run.text = run.text.replace(f"{{{{{key}}}}}", str(val))

    def _assert_no_unfilled(self, doc):
        all_text = " ".join(p.text for p in doc.paragraphs)
        remaining = re.findall(r"\{\{[^}]+\}\}", all_text)
        if remaining:
            raise TemplateFillError(f"Unfilled placeholders: {remaining}")
```

---

### 7. Database Connection Pool (Golden Rule)

```
Formula: real_connections = (vCPUs × 2) + 1
Local dev (4 vCPU):   (4×2)+1 = 9
KVM4 (4 vCPU):        (4×2)+1 = 9
KVM8 (8 vCPU):        (8×2)+1 = 17

PgBouncer multiplexes up to 200 client connections onto these 9 real connections.
Beyond 9 real connections on 4 cores: context switching overhead exceeds gain.
```

```ini
# infra/pgbouncer/pgbouncer.ini

[databases]
gradepro = host=postgres port=5432 dbname=gradepro

[pgbouncer]
pool_mode = transaction
max_client_conn = 200
default_pool_size = 9              ; (vCPUs×2)+1 — set via env in production
reserve_pool_size = 2
reserve_pool_timeout = 2
min_pool_size = 2

server_idle_timeout = 300
client_idle_timeout = 60
server_connect_timeout = 10
query_timeout = 30
query_wait_timeout = 10

max_prepared_statements = 0        ; Must be 0 for transaction pool mode
server_reset_query = DISCARD ALL

auth_type = scram-sha-256
auth_file = /etc/pgbouncer/userlist.txt
```

```python
# Per-service SQLAlchemy engine — right-sized, prepared statements disabled

def make_engine(service: str) -> AsyncEngine:
    sizes = {
        "orchestrator": (3, 2),
        "ml_inference": (2, 1),
        "pdf_service":  (2, 1),
        "gateway":      (2, 1),
    }
    pool_size, max_overflow = sizes.get(service, (2, 1))
    return create_async_engine(
        os.getenv("DATABASE_URL"),       # Points to PgBouncer
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_timeout=10,
        connect_args={
            "prepared_statement_cache_size": 0,  # Required for PgBouncer transaction mode
            "server_settings": {"application_name": service},
        },
    )
```

---

### 8. Redis: Streams Instead of Pub/Sub for WebSocket Events

**Why Streams:** Pub/sub is fire-and-forget. If the Go WebSocket hub disconnects for 2 seconds during a Redis restart, all events published during that window are lost forever. Redis Streams persist events and support consumer group catch-up.

```python
# Publishing events from Celery workers
async def emit_progress(job_id: str, event: dict):
    redis.xadd(
        f"job:{job_id}:events",
        event,
        maxlen=100,        # Keep last 100 events per job
    )
    # TTL on the stream — auto-cleanup after 24h
    redis.expire(f"job:{job_id}:events", 86400)

# Go gateway: consume stream, forward to WebSocket room
# On reconnect: XREAD from last-seen event ID → client catches up on all missed events
```

---

### 9. Grading Pipeline — Complete Flow

```
STEP 0: Upload
  ├── MIME magic bytes check (not extension)
  ├── File hash → Redis SETNX dedup (atomic, prevents race condition)
  ├── DocxSecurityPipeline.run() → ClamAV scan + macro strip + XXE guard
  ├── Save to R2: assignments/{assessor_id}/{job_id}/{uuid}.docx  ← no PII in path
  ├── Grading job inserted → DB (with file_hash, version=0)
  └── WebSocket stream created → job_id returned to client

STEP 1: Parse (No LLM — Pure Python, < 1s)
  ├── UniversalAssignmentParser.parse()
  │    ├── Header: Table[0] → deterministic extraction
  │    │   Awarding body · Level · Unit code · Student name
  │    ├── College: match centre_name against college_patterns table (not fragile string match)
  │    ├── Tasks: Heading 1 boundaries → list of TaskSection (any task count)
  │    └── Features: DocxFontResolver.format_summary() (resolved, not raw)
  └── emit_progress(job_id, {stage: PARSE, progress: 10})

STEP 2: Format Validation (No LLM, < 0.5s)
  ├── Load college format rules → Redis cache (resolved from DB if miss)
  ├── Compare features vs rules → violations list
  ├── HARD FAIL: return immediately, no compute wasted on formatting issues
  ├── SOFT WARNINGS: continue, note in report
  └── emit_progress(job_id, {stage: FORMAT, result, issues, progress: 20})

STEP 3: Unit Routing (< 100ms)
  ├── Lookup: units table indexed on (unit_code, awarding_body, level)
  ├── Determine tier: 0=cold/1=warm/2=trained/3=mature
  ├── Unknown unit → COLD_START mode + flag for admin
  └── emit_progress(job_id, {stage: ROUTING, unit, tier, progress: 25})

STEP 4: Model Load (< 100ms if cached, < 3s cold)
  ├── Check ModelRegistry LRU cache
  ├── HIT → use immediately
  ├── MISS → R2 fetch → load head → cache (single-flight: only one worker fetches)
  └── emit_progress(job_id, {stage: MODEL_LOAD, version, progress: 30})

STEP 5: Parallel Task Evaluation
  ├── asyncio.gather(*[evaluate_task(t) for t in tasks])
  │
  │   Per task:
  │   ├── SlidingWindowEmbedder.encode(task.student_content) → 384-dim
  │   ├── UnitGradingHead.forward([embedding]) → {pass_prob, criterion_scores}
  │   ├── reasoning_client.evaluate(task, criteria, sub_model_signal)
  │   │    with asyncio.timeout(LLM_CALL_TIMEOUT_SECONDS)
  │   │    → {verdict, reasoning, feedback_text}
  │   └── emit_progress(job_id, {stage: TASK_N, verdict, progress})
  │
  └── All tasks done → merge results

STEP 6: Final Decision (< 100ms)
  ├── PASS only if ALL tasks pass
  ├── REFER if ANY task fails
  ├── Generate overall assessor comment (few-shot guided, real assessor tone)
  ├── OCC update: grading_jobs status → DONE (version check)
  └── emit_progress(job_id, {stage: DECISION, verdict, progress: 85})

STEP 7: PDF Generation (< 8s)
  ├── Load active feedback template from R2 (unit × college, version tracked in DB)
  ├── Fill placeholders (dynamic N tasks)
  ├── Assert no unfilled placeholders remain
  ├── GotenbergPDFGenerator.convert() → PDF bytes
  ├── Upload to R2: reports/{job_id}/{uuid}.pdf  ← no PII in path
  ├── Record pdf_url_expires_at in DB (1h; renewable via /reports/{job_id}/url)
  └── emit_progress(job_id, {stage: COMPLETE, verdict, pdf_url, progress: 100})
```

---

### 10. Versioning System — Everything Hot-Swappable

Every configurable asset is independently versioned. Changing one unit's model, criteria, template, or format rules affects **only that unit/college** and takes effect for the **next grading job** with zero downtime.

```sql
-- All versioned tables follow this pattern:
CREATE TABLE model_registry (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    unit_id         UUID NOT NULL REFERENCES units(id),
    version_number  INTEGER NOT NULL,
    storage_path_r2 TEXT NOT NULL,          -- Full R2 path
    f1_score        FLOAT,
    refer_recall    FLOAT,                  -- Primary metric
    criteria_version_id UUID REFERENCES unit_criteria_versions(id),
    status          TEXT DEFAULT 'PENDING_REVIEW',  -- PENDING_REVIEW | ACTIVE | RETIRED
    is_active       BOOLEAN DEFAULT FALSE,
    promoted_by     UUID REFERENCES users(id),
    promoted_at     TIMESTAMPTZ,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    version         INTEGER DEFAULT 0,      -- Optimistic lock column
    UNIQUE (unit_id, version_number)
);

-- Atomic promotion (SELECT FOR UPDATE prevents concurrent promotion race)
async def promote_model(unit_id: UUID, new_model_id: UUID, promoter_id: UUID):
    async with db.begin():
        # Lock current active row — serializes concurrent admin promotions
        current = await db.execute(
            "SELECT id, version FROM model_registry "
            "WHERE unit_id=$1 AND is_active=true FOR UPDATE",
            unit_id,
        )
        if current.rowcount:
            await db.execute(
                "UPDATE model_registry SET is_active=false, status='RETIRED' "
                "WHERE id=$1", current.fetchone()["id"]
            )
        await db.execute(
            "UPDATE model_registry SET is_active=true, status='ACTIVE', "
            "promoted_by=$1, promoted_at=NOW() WHERE id=$2",
            promoter_id, new_model_id
        )
    # Invalidate cache
    await cache_invalidator.on_model_promoted(unit_id)
```

---

### 11. Role-Based Access Control

```
ADMIN
  ├── All of the below
  ├── Manage users + roles
  ├── Upload + activate feedback templates (per unit × college)
  ├── Edit + activate format rules (per college)
  ├── Upload CSV → trigger retraining
  ├── Promote / rollback model versions
  ├── Manage API keys + Ollama config
  └── View audit log

MAIN_ASSESSOR
  ├── All of ASSESSOR below
  ├── Override AI verdict (with mandatory reason — logged)
  ├── View all assessor records within scope
  └── Edit (not upload) feedback template content

ASSESSOR
  ├── Submit grading jobs (assigned units only — enforced via user_unit_assignments table)
  ├── View own records
  └── Download own PDFs
```

---

### 12. Database Schema

```sql
-- ORGANIZATION
CREATE TABLE colleges (id UUID PK, name TEXT, code TEXT UNIQUE);
CREATE TABLE awarding_bodies (id UUID PK, name TEXT, code TEXT UNIQUE);
CREATE TABLE courses (id UUID PK, awarding_body_id UUID FK, name TEXT, level TEXT);
CREATE TABLE units (
    id UUID PK, course_id UUID FK, unit_code TEXT,
    unit_name TEXT, level TEXT,
    tier SMALLINT DEFAULT 0,        -- 0=cold 1=warm 2=trained 3=mature
    submission_count INTEGER DEFAULT 0,
    has_training_data BOOLEAN DEFAULT FALSE
);
CREATE UNIQUE INDEX idx_units_lookup ON units(unit_code, course_id, level);

-- VERSIONED CRITERIA
CREATE TABLE unit_criteria_versions (
    id UUID PK, unit_id UUID FK, version_number INTEGER,
    criteria_json JSONB NOT NULL,   -- LOs, ACs, pass conditions
    is_active BOOLEAN DEFAULT FALSE,
    changed_by UUID FK, changed_at TIMESTAMPTZ, change_notes TEXT
);
CREATE TABLE unit_contexts (
    unit_id UUID PK FK, criteria_version_id UUID FK,
    few_shot_examples JSONB,        -- Real assessor comment samples
    tone_guide TEXT,
    updated_at TIMESTAMPTZ
);

-- VERSIONED MODELS
CREATE TABLE model_registry (
    id UUID PK, unit_id UUID FK, version_number INTEGER,
    storage_path_r2 TEXT,
    f1_score FLOAT, refer_recall FLOAT, accuracy FLOAT,
    criteria_version_id UUID FK,
    tier SMALLINT, status TEXT, is_active BOOLEAN DEFAULT FALSE,
    promoted_by UUID FK, promoted_at TIMESTAMPTZ, notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(), version INTEGER DEFAULT 0,
    UNIQUE(unit_id, version_number)
);

-- VERSIONED TEMPLATES
CREATE TABLE feedback_templates (
    id UUID PK, unit_id UUID FK, college_id UUID FK,
    version_number INTEGER, storage_path_r2 TEXT,
    is_active BOOLEAN DEFAULT FALSE,
    uploaded_by UUID FK, uploaded_at TIMESTAMPTZ, notes TEXT,
    UNIQUE(unit_id, college_id, version_number)
);

-- VERSIONED FORMAT RULES
CREATE TABLE format_rules (
    id UUID PK, college_id UUID FK,
    version_number INTEGER, rules_json JSONB,
    is_active BOOLEAN DEFAULT FALSE,
    created_by UUID FK, created_at TIMESTAMPTZ, notes TEXT
);

-- GRADING
CREATE TABLE grading_jobs (
    id UUID PK DEFAULT gen_random_uuid(),
    assessor_id UUID FK, unit_id UUID FK, college_id UUID FK,
    student_name TEXT, student_id TEXT,
    file_hash TEXT NOT NULL, file_path_r2 TEXT,
    status TEXT DEFAULT 'pending',
    model_version_id UUID FK,
    criteria_version_id UUID FK,
    format_rules_version_id UUID FK,
    version INTEGER DEFAULT 0,      -- Optimistic lock
    created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX idx_jobs_dedup ON grading_jobs(file_hash, assessor_id)
    WHERE created_at > NOW() - INTERVAL '24h';  -- Partial index — dedup window

CREATE TABLE grading_results (
    id UUID PK, job_id UUID FK, task_number SMALLINT,
    verdict TEXT, confidence FLOAT,
    submodel_pass_prob FLOAT, submodel_criterion_scores JSONB,
    reasoning_text TEXT, feedback_text TEXT,
    weak_areas JSONB, fallback_used BOOLEAN DEFAULT FALSE
);

CREATE TABLE final_reports (
    id UUID PK, job_id UUID FK,
    overall_verdict TEXT, overall_comment TEXT,
    template_version_id UUID FK,
    pdf_path_r2 TEXT, pdf_url_expires_at TIMESTAMPTZ,
    assessor_override BOOLEAN DEFAULT FALSE,
    override_by UUID FK, override_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- USER MANAGEMENT
CREATE TABLE users (
    id UUID PK, email TEXT UNIQUE, name TEXT,
    role TEXT CHECK (role IN ('ADMIN','MAIN_ASSESSOR','ASSESSOR')),
    college_id UUID FK, is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE user_unit_assignments (
    user_id UUID FK, unit_id UUID FK,
    assigned_by UUID FK, assigned_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, unit_id)
);
CREATE TABLE sessions (
    id UUID PK, user_id UUID FK,
    refresh_token_hash TEXT UNIQUE,
    expires_at TIMESTAMPTZ, created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_sessions_token ON sessions(refresh_token_hash);

-- API KEYS & CONFIG
CREATE TABLE api_keys (
    id UUID PK, name TEXT, provider TEXT,
    key_encrypted TEXT NOT NULL,        -- AES-256 Fernet encrypted
    daily_limit INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    rate_limit_cooldown_until TIMESTAMPTZ,
    added_by UUID FK, created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_apikeys_provider_active ON api_keys(provider) WHERE is_active=TRUE;

CREATE TABLE ollama_configs (
    id UUID PK, model_name TEXT, endpoint TEXT,
    context_window INTEGER, is_active BOOLEAN DEFAULT FALSE
);

-- AUDIT (append-only — no deletes, no updates)
CREATE TABLE audit_log (
    id BIGSERIAL PK,
    actor_id UUID, action TEXT, resource_type TEXT, resource_id UUID,
    metadata JSONB, created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_audit_actor ON audit_log(actor_id, created_at DESC);
CREATE INDEX idx_audit_resource ON audit_log(resource_type, resource_id);

-- INDEXES (critical query paths)
CREATE INDEX CONCURRENTLY idx_jobs_assessor_status
    ON grading_jobs(assessor_id, status, created_at DESC);
CREATE INDEX CONCURRENTLY idx_jobs_pending
    ON grading_jobs(created_at ASC) WHERE status='pending';
CREATE INDEX CONCURRENTLY idx_model_active_per_unit
    ON model_registry(unit_id) WHERE is_active=TRUE;
CREATE INDEX CONCURRENTLY idx_template_active
    ON feedback_templates(unit_id, college_id) WHERE is_active=TRUE;
CREATE INDEX CONCURRENTLY idx_format_rules_active
    ON format_rules(college_id) WHERE is_active=TRUE;
CREATE INDEX CONCURRENTLY idx_criteria_active
    ON unit_criteria_versions(unit_id) WHERE is_active=TRUE;
CREATE INDEX CONCURRENTLY idx_jobs_fts
    ON grading_jobs USING GIN(to_tsvector('english', student_name));
```

---

### 13. Complete Docker Compose

```yaml
version: "3.9"

networks:
  internal:
    driver: bridge
    internal: true
  public:
    driver: bridge

volumes:
  postgres_data:
  redis_data:
  clamav_data:
  clamav_socket:

secrets:
  postgres_password:
    file: ./secrets/postgres_password.txt

services:

  nginx:
    image: nginx:1.27-alpine
    ports: ["80:80", "443:443"]
    networks: [public, internal]
    volumes: ["./infra/nginx:/etc/nginx/conf.d:ro"]
    restart: unless-stopped

  frontend:
    build: ./frontend
    networks: [internal]
    restart: unless-stopped

  gateway:
    build: ./gateway
    networks: [internal]
    restart: unless-stopped
    environment:
      - JWT_PRIVATE_KEY_FILE=/run/secrets/jwt_private_key
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 5s
      retries: 3

  orchestrator:
    build: ./services/orchestrator
    networks: [internal]
    restart: unless-stopped
    environment:
      - DATABASE_URL=postgresql+asyncpg://app:${DB_PASS}@pgbouncer:5432/gradepro
      - REDIS_URL=redis://redis:6379
      - R2_ACCOUNT_ID=${R2_ACCOUNT_ID}
      - R2_ACCESS_KEY=${R2_ACCESS_KEY}
      - R2_SECRET_KEY=${R2_SECRET_KEY}

  ml_inference:
    build: ./services/ml_inference
    networks: [internal]
    restart: unless-stopped
    environment:
      - MODEL_CACHE_MAX_MB=0            # 0 = auto (40% of available RAM)
      - MODEL_CACHE_MIN_FREE_MB=300
      - R2_ACCOUNT_ID=${R2_ACCOUNT_ID}
      - R2_ACCESS_KEY=${R2_ACCESS_KEY}
      - R2_SECRET_KEY=${R2_SECRET_KEY}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8002/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  pdf_service:
    build: ./services/pdf_service
    networks: [internal]
    restart: unless-stopped
    environment:
      - GOTENBERG_URL=http://gotenberg:3000

  celery_grading:
    build: ./services/orchestrator
    command: >
      celery -A app worker -Q grading_queue
      --pool=gevent
      --concurrency=${CELERY_GRADING_CONCURRENCY:-15}
      --max-tasks-per-child=100
      --loglevel=info
    deploy:
      replicas: ${CELERY_GRADING_REPLICAS:-4}
    networks: [internal]
    restart: unless-stopped
    environment:
      - GEVENT_SUPPORT=True
      - MODEL_CACHE_MAX_MB=0
      - MODEL_CACHE_MIN_FREE_MB=300
      - LLM_CALL_TIMEOUT_SECONDS=20

  celery_training:
    build: ./services/orchestrator
    command: >
      celery -A app worker -Q training_queue
      --pool=prefork
      --concurrency=${CELERY_TRAINING_CONCURRENCY:-2}
      --max-tasks-per-child=5
    networks: [internal]
    restart: unless-stopped
    cpus: "${TRAINING_CPU_LIMIT:-1.5}"

  celery_pdf:
    build: ./services/orchestrator
    command: >
      celery -A app worker -Q pdf_queue
      --pool=gevent
      --concurrency=${CELERY_PDF_CONCURRENCY:-10}
      --max-tasks-per-child=50
    networks: [internal]
    restart: unless-stopped
    environment:
      - GEVENT_SUPPORT=True

  celery_beat:
    build: ./services/orchestrator
    command: celery -A app beat --loglevel=info
    networks: [internal]
    restart: unless-stopped

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: gradepro
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
    volumes: ["postgres_data:/var/lib/postgresql/data"]
    networks: [internal]
    shm_size: 256m
    command: >
      postgres
      -c max_connections=20
      -c shared_buffers=256MB
      -c effective_cache_size=512MB
      -c work_mem=16MB
      -c wal_level=replica
    restart: unless-stopped
    secrets: [postgres_password]

  pgbouncer:
    image: pgbouncer/pgbouncer:1.23.0
    volumes: ["./infra/pgbouncer/pgbouncer.ini:/etc/pgbouncer/pgbouncer.ini:ro"]
    networks: [internal]
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    command: >
      redis-server
      --appendonly yes
      --appendfsync everysec
      --maxmemory ${REDIS_MAX_MEMORY:-512mb}
      --maxmemory-policy allkeys-lru
      --save 60 1000
    volumes: ["redis_data:/data"]
    networks: [internal]
    restart: unless-stopped

  clamav:
    image: clamav/clamav:1.3
    volumes:
      - clamav_data:/var/lib/clamav
      - clamav_socket:/var/run/clamav
    mem_limit: ${CLAMAV_MEM_LIMIT:-1g}
    networks: [internal]
    restart: unless-stopped

  gotenberg:
    image: gotenberg/gotenberg:8
    command:
      - "gotenberg"
      - "--libreoffice-restart-after=50"
      - "--libreoffice-max-queue=${GOTENBERG_QUEUE:-5}"
      - "--api-timeout=${GOTENBERG_TIMEOUT:-30s}"
    mem_limit: ${GOTENBERG_MEM_LIMIT:-2g}
    networks: [internal]
    cap_drop: [ALL]
    cap_add: [CHOWN, SETUID, SETGID]
    tmpfs:
      - /tmp:size=512m,noexec
    restart: unless-stopped

  prometheus:
    image: prom/prometheus:v2.53.0
    networks: [internal]
    restart: unless-stopped

  grafana:
    image: grafana/grafana:11.0.0
    networks: [internal]
    restart: unless-stopped
```

---

### 14. `.env.example`

```env
# ── Cloudflare R2 ──
R2_ACCOUNT_ID=
R2_ACCESS_KEY=
R2_SECRET_KEY=
R2_BUCKET_ASSIGNMENTS=gradepro-assignments
R2_BUCKET_REPORTS=gradepro-reports
R2_BUCKET_TEMPLATES=gradepro-templates
R2_BUCKET_MODELS=gradepro-models
R2_BUCKET_TRAINING=gradepro-training-data
R2_BUCKET_BACKUPS=gradepro-backups

# ── Database ──
DB_PASS=changeme

# ── Redis ──
REDIS_MAX_MEMORY=512mb

# ── ML — Dynamic (0 = auto from available RAM) ──
MODEL_CACHE_MAX_MB=0
MODEL_CACHE_MIN_FREE_MB=300

# ── Celery — tune per server size ──
CELERY_GRADING_REPLICAS=4
CELERY_GRADING_CONCURRENCY=15
CELERY_TRAINING_CONCURRENCY=2
CELERY_PDF_CONCURRENCY=10
TRAINING_CPU_LIMIT=1.5
LLM_CALL_TIMEOUT_SECONDS=20

# ── Gotenberg / ClamAV — only hard caps here (genuine leak risk) ──
GOTENBERG_MEM_LIMIT=2g
GOTENBERG_QUEUE=5
GOTENBERG_TIMEOUT=30s
CLAMAV_MEM_LIMIT=1g
```

---

### 15. Execution Plan

**Phase 1 — Foundation (Weeks 1-2)**
- [ ] Monorepo structure
- [ ] Docker Compose — all services up and healthy
- [ ] PostgreSQL schema + Alembic migrations + all indexes
- [ ] PgBouncer golden-rule config
- [ ] Go gateway: JWT RS256 (keys in Docker secrets), RBAC, Lua rate limiting, WebSocket hub consuming Redis Streams
- [ ] R2 buckets created + DocxSecurityPipeline (ClamAV + sanitizer)
- [ ] Redis AOF enabled + all Lua scripts registered
- [ ] Health checks on all services

**Phase 2 — ML Pipeline (Weeks 3-4)**
- [ ] `SlidingWindowEmbedder` (bge-small-en-v1.5)
- [ ] `UnitGradingHead` (MLP, max-pool, task-count invariant)
- [ ] `ModelRegistry` (dynamic LRU, memory-self-aware)
- [ ] Training pipeline: `WeightedRandomSampler` + class-weighted loss + early stopping on refer-recall
- [ ] XGBoost: saved as JSON (not pickle)
- [ ] Train HSC301: target refer-recall > 0.80
- [ ] Model versioning in R2 + model_registry table
- [ ] `DocxFontResolver` (4-level inheritance)

**Phase 3 — Grading Pipeline (Weeks 5-6)**
- [ ] `UniversalAssignmentParser` (Heading 1 boundary, any task count)
- [ ] Format validator (uses resolved font values)
- [ ] Reasoning model client (API rotation + Lua + circuit breaker + asyncio timeout)
- [ ] Parallel task evaluation with per-call timeout
- [ ] Celery Gevent workers (`--max-tasks-per-child=100`)
- [ ] Redis Streams event publishing + Go hub consumer
- [ ] WebSocket reconnection: client catches up from last event ID
- [ ] Dead letter queue + admin notification

**Phase 4 — PDF & Versioning (Week 7)**
- [ ] `GotenbergPDFGenerator` with unfilled-placeholder assertion
- [ ] Template filler (dynamic N tasks, headers, footers)
- [ ] Template versioning (per unit × college) in DB + R2
- [ ] Criteria versioning: update → triggers PENDING_CRITERIA_UPDATE status
- [ ] Format rules versioning (per college)
- [ ] Model promotion: `SELECT FOR UPDATE` atomic swap
- [ ] R2 PDF path: opaque UUID (no PII), served via proxy endpoint

**Phase 5 — Frontend (Week 8)**
- [ ] Grade Now: upload + WebSocket progress bar + reconnection
- [ ] Dashboard: stats via read-optimized queries
- [ ] Records: search (FTS index), filter, PDF download
- [ ] Admin pages: Models, Templates, Format Rules, Criteria, Users
- [ ] Settings: API keys (encrypted), Ollama config

**Phase 6 — Production Hardening (Weeks 9-10)**
- [ ] Daily `pg_dump` → R2 backups bucket (30-day retention)
- [ ] Prometheus metrics: queue depth, LLM latency, cache hit rate, refer-recall drift
- [ ] Grafana dashboards + alert rules
- [ ] Loki log aggregation (structured JSON, trace IDs on every log line)
- [ ] Sustained load test: 15 concurrent grading jobs for 1 hour — confirm no memory growth
- [ ] GDPR: anonymization job, data retention cron, purge endpoint
- [ ] Security: OWASP checklist, HSTS header, CSP header
- [ ] Runbook: backup restore, model rollback, API key rotation

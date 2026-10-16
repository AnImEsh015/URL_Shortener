# Production-Style URL Shortener & Analytics Platform

[![CI](https://github.com/AnImEsh015/URL_Shortener/actions/workflows/ci.yml/badge.svg)](https://github.com/AnImEsh015/URL_Shortener/actions/workflows/ci.yml)
[![Live Demo](https://img.shields.io/badge/Render-Live%20Demo-46E3B7.svg)](https://url-shortener-99ta.onrender.com/docs)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D.svg)](https://redis.io/)
[![Coverage](https://img.shields.io/badge/Coverage-88%25-brightgreen.svg)]()

> 🚀 **Live Production API**: [https://url-shortener-99ta.onrender.com](https://url-shortener-99ta.onrender.com)  
> 📖 **Interactive Swagger UI**: [https://url-shortener-99ta.onrender.com/docs](https://url-shortener-99ta.onrender.com/docs)  
> 🏥 **Health Check**: [https://url-shortener-99ta.onrender.com/health](https://url-shortener-99ta.onrender.com/health)  
> *(Deployed on Render Free Tier with Render PostgreSQL & Render Key Value / Valkey)*

A production-style URL shortener and click-analytics backend engineered with simplicity, maintainability, and horizontal scalability in mind. Built with **Python 3.12**, **FastAPI**, **PostgreSQL 16**, **Redis 7**, and **Celery 5**.

The codebase is written with plain `def` endpoints and synchronous SQLAlchemy 2.x models to maintain predictable threading behavior and avoid async ORM traps. Every architectural decision is explicitly documented with the **"WHY"** behind it to serve as a comprehensive portfolio piece and interview reference.

---

## Architecture

The system decouples low-latency redirection from background analytics processing via an asynchronous Celery task queue backed by Redis.

```mermaid
flowchart TD
    Client(["User / Client Browser"])

    subgraph API_Gateway ["FastAPI Application"]
        MW["Request-ID Middleware & Rate Limiter"]
        AuthRouter["/auth (Register, Login)"]
        LinkRouter["/api/links (CRUD, QR)"]
        RedirectRouter["/{short_code} (302 Redirect)"]
        StatsRouter["/api/links/{id}/stats (Aggregations)"]
    end

    subgraph Cache_Layer ["Redis 7"]
        Cache[("Link Cache: link:{code}<br/>Negative Cache (60s)<br/>Click Counter: link:{id}:clicks<br/>Sliding Window Rate Limits")]
        Broker[("Celery Task Broker & Queue")]
    end

    subgraph Storage_Layer ["PostgreSQL 16"]
        UsersTbl[("users Table")]
        LinksTbl[("links Table")]
        ClicksTbl[("clicks Table<br/>(Composite Index: link_id, clicked_at)")]
    end

    subgraph Background_Worker ["Celery Analytics Worker"]
        Task["record_click Task<br/>HMAC-SHA256 IP Hash<br/>User-Agent Parser<br/>GeoIP Resolver"]
    end

    Client -->|"HTTP Request (X-Request-ID)"| MW
    MW --> AuthRouter
    MW --> LinkRouter
    MW --> RedirectRouter
    MW --> StatsRouter

    RedirectRouter -->|"1. Cache-Aside Check"| Cache
    RedirectRouter -->|"2. Fallback on Miss"| LinksTbl
    RedirectRouter -->|"3. Enqueue Event"| Broker
    RedirectRouter -->|"4. 302 Location Header"| Client

    Broker --> Task
    Task -->|"Atomic increment click_count & insert Click"| LinksTbl
    Task -->|"Insert analytics row"| ClicksTbl

    StatsRouter -->|"Cached Stats Check"| Cache
    StatsRouter -->|"Parameterized Aggregations"| ClicksTbl
```

---

## Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| **Language** | Python 3.12 | Modern type hints, `StrEnum`, UTC improvements, performance gains. |
| **Framework** | FastAPI + Uvicorn | High-performance ASGI framework with automatic OpenAPI documentation. |
| **Settings** | Pydantic v2 + Pydantic Settings | Strictly typed configuration loaded directly from environment variables. |
| **Primary Database** | PostgreSQL 16 | Relational consistency, foreign key cascades, time-bucketed indexing. |
| **ORM & Migrations** | SQLAlchemy 2.x (Sync) + Alembic | Declarative 2.0 typed models (`Mapped`, `mapped_column`) and automated migrations. |
| **In-Memory Cache** | Redis 7 (`redis-py`) | Sub-millisecond cache-aside lookups, sliding-window rate limiting, and counters. |
| **Task Queue** | Celery 5 (Redis broker) | Asynchronous background processing for non-blocking 302 redirects. |
| **Security** | `bcrypt` (direct) + `PyJWT` (HS256) | Robust password hashing without deprecated wrappers (`passlib`), stateless JWT auth. |
| **Analytics & Extras** | `user-agents`, `geoip2`, `qrcode[pil]` | Device/OS categorization, geographic IP lookup, and QR PNG generation. |
| **Testing & Quality** | `pytest`, `pytest-cov`, `fakeredis`, `ruff`, `locust` | 88% measured test coverage, strict zero-warning linting, and load testing. |

---

## Quickstart (Docker Compose)

The fastest way to spin up the entire cluster (API, Celery worker, PostgreSQL, Redis) is using Docker Compose.

### 1. Clone & Configure
```bash
git clone https://github.com/AnImEsh015/URL_Shortener.git
cd URL_Shortener
cp .env.example .env
```

### 2. Launch the Stack
```bash
docker compose up --build -d
```

### 3. Verify Health & Explore
- **Health Check**: `curl -i http://localhost:8000/health`
- **Interactive Swagger Documentation**: Open `http://localhost:8000/docs` in your browser.
- **Redoc Documentation**: Open `http://localhost:8000/redoc`.

---

## Environment Variables

All settings are configured via environment variables and loaded into `app/config.py`:

| Variable | Type | Default | Description |
|---|---|---|---|
| `ENV` | `str` | `development` | Runtime environment (`development`, `production`, `test`). |
| `PROJECT_NAME` | `str` | `Production URL Shortener` | Title displayed in Swagger docs and logs. |
| `BASE_URL` | `str` | `http://localhost:8000` | Public service origin used for generating short link URLs. |
| `DATABASE_URL` | `str` | `postgresql://postgres:postgres@localhost:5432/shortener` | PostgreSQL primary connection string. |
| `TEST_DATABASE_URL` | `str` | `postgresql://postgres:postgres@localhost:5432/shortener_test` | Isolated database connection string for `pytest`. |
| `REDIS_URL` | `str` | `redis://localhost:6379/0` | Redis connection URL for caching and rate limiting. |
| `CELERY_BROKER_URL` | `str` | `redis://localhost:6379/1` | Redis broker URL for Celery task queuing. |
| `CELERY_RESULT_BACKEND` | `str` | `redis://localhost:6379/2` | Redis backend URL for Celery task states. |
| `CELERY_ALWAYS_EAGER` | `bool` | `false` | When `true`, executes Celery tasks inline synchronously (used in tests). |
| `JWT_SECRET` | `str` | *(placeholder)* | Secret key for signing HS256 JWTs (refuses to start if default in production). |
| `JWT_ALGORITHM` | `str` | `HS256` | JWT signing algorithm. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `int` | `30` | Access token lifespan in minutes. |
| `IP_HASH_SALT` | `str` | *(placeholder)* | Secret salt for HMAC-SHA256 IP address anonymization. |
| `TRUSTED_PROXY` | `bool` | `false` | When `true`, trusts the first IP in `X-Forwarded-For`. |
| `REJECT_PRIVATE_IPS` | `bool` | `true` | When `true`, forbids shortening localhost, loopback, or private RFC1918 IPs. |
| `CACHE_ENABLED` | `bool` | `true` | Master switch for Redis metadata and stats caching. |
| `RATE_LIMIT_LOGIN_PER_MIN` | `int` | `5` | Maximum login attempts per IP per minute. |
| `RATE_LIMIT_REGISTER_PER_HOUR` | `int` | `5` | Maximum registration attempts per IP per hour. |
| `RATE_LIMIT_LINK_CREATE_PER_HOUR` | `int` | `20` | Maximum link creations per authenticated user per hour. |
| `RATE_LIMIT_REDIRECT_PER_MIN` | `int` | `300` | Maximum redirects served per client IP per minute. |
| `GEOIP_DB_PATH` | `str` | `None` | Path to optional MaxMind `GeoLite2-City.mmdb` binary file. |
| `CORS_ORIGINS` | `str` | `*` | Comma-delimited list of allowed CORS origins. |

---

## API Endpoints

| Method | Path | Auth Required | Description | Status Codes |
|---|---|:---:|---|---|
| `GET` | `/health` | No | Deep health probe verifying PostgreSQL and Redis | `200`, `503` |
| `POST` | `/auth/register` | No | Register new account (lowercase email, hashed password) | `201`, `400`, `409`, `429` |
| `POST` | `/auth/login` | No | OAuth2 password flow login (returns JWT access token) | `200`, `401`, `429` |
| `POST` | `/api/links` | **Yes** | Create shortened link with custom alias & expiration | `201`, `400`, `401`, `409`, `429` |
| `GET` | `/api/links` | **Yes** | Paginated listing of links owned by current user | `200`, `401` |
| `GET` | `/api/links/{id}` | **Yes** | Retrieve single link details (isolated ownership) | `200`, `401`, `404` |
| `PATCH` | `/api/links/{id}` | **Yes** | Update `is_active`, `expires_at`, or `max_clicks` | `200`, `400`, `401`, `404` |
| `DELETE` | `/api/links/{id}` | **Yes** | Delete link and purge cache key | `204`, `401`, `404` |
| `GET` | `/api/links/{id}/stats` | **Yes** | Overview metrics (total clicks, unique visitors, time bounds) | `200`, `401`, `404` |
| `GET` | `/api/links/{id}/stats/timeseries` | **Yes** | Chronological click counts bucketed by `day` or `hour` | `200`, `401`, `404` |
| `GET` | `/api/links/{id}/stats/breakdown` | **Yes** | Categorical breakdown by `country`, `device`, `browser`, `os`, `referrer` | `200`, `401`, `404` |
| `GET` | `/api/links/{id}/qr` | **Yes** | High-contrast PNG QR code image of short link | `200`, `401`, `404` |
| `GET` | `/{short_code}` | No | High-throughput redirect to target URL | `302`, `404`, `410`, `429` |

---

## Key Design Decisions & Interview Questions

### 1. Why HTTP 302 Found instead of 301 Moved Permanently?
- **HTTP 301 (Moved Permanently)** instructs browsers and intermediate proxies to cache the redirect destination indefinitely. If a 301 is returned, subsequent clicks by the same user will bypass the URL shortener entirely and go straight to the target site. This would break real-time click tracking, bypass link deactivation (`is_active=False`), and prevent expiration enforcement.
- **HTTP 302 (Found)** ensures that every single request hits our gateway first, allowing us to enforce access controls, evaluate rate limits, and record analytics.

### 2. Why 7-Character Base62 Short Codes?
- Characters: `[a-zA-Z0-9]` ($26 + 26 + 10 = 62$ characters).
- Key Space: $62^7 = 3,521,614,606,208 \approx 3.52 \text{ trillion}$ unique combinations.
- Random generation using Python's `secrets` module ensures cryptographic unpredictability (preventing attackers from guessing or scraping sequential short links).
- Collision protection is backed by a database `UNIQUE` constraint index on `links.short_code` with up to 5 automatic insertion retries.

### 3. Why Cache-Aside with Negative Caching?
- **Cache-Aside Pattern**: On a redirect request, the API checks Redis key `link:{short_code}`. On a cache hit, it redirects immediately without querying PostgreSQL. On a cache miss, it reads PostgreSQL, writes the metadata to Redis with a dynamic TTL (`min(3600, seconds_until_expiry)`), and returns the redirect.
- **Negative Caching**: If a requested short code does not exist in the database, the API caches `{"status": "not_found"}` in Redis for 60 seconds. This protects the relational database from Cache Penetration attacks (where malicious actors flood non-existent short codes to exhaust DB connection pools).

### 4. Why Sliding-Window Rate Limiting via Redis Sorted Sets?
- Fixed-window rate limiting (e.g. counter reset at the start of each minute) is susceptible to boundary burst attacks: a user could make 100% of their quota in the last second of minute 1 and another 100% in the first second of minute 2, doubling the permitted traffic.
- Our sliding-window rate limiter stores timestamps in a Redis Sorted Set (`ZSET`). Using an atomic Redis pipeline (`ZREMRANGEBYSCORE`, `ZADD`, `ZCARD`, `EXPIRE`), it evaluates the exact number of requests that occurred in the preceding $N$ seconds. If exceeded, it calculates the exact `Retry-After` duration based on the oldest element in the window.
- **Fail-Open Policy**: If Redis is temporarily unreachable, the rate limiter logs a warning and allows requests through to avoid taking down the service.

### 5. Why Asynchronous Background Processing for Analytics?
- Redirect performance is paramount. An end-user clicking a short link should not wait for user-agent string parsing, GeoIP disk lookups, and disk writes to complete.
- The API enqueues a lightweight message into Celery (`record_click.delay(...)`) and issues the `302 Found` response in under a few milliseconds. The worker process performs HMAC-SHA256 hashing, GeoIP lookup, and commits the `Click` row asynchronously.

### 6. Why Return 404 Instead of 403 on Unauthorized Link Access?
- If User B attempts to access, patch, or delete User A's link (`/api/links/{id}`), returning `403 Forbidden` reveals that a link with ID `{id}` exists in the system (information disclosure / IDOR enumeration).
- Returning `404 Not Found` makes unauthorized resources completely indistinguishable from non-existent resources.

### 7. Why Approximate `max_clicks` via Redis Atomic Counter?
- Tracking `max_clicks` with strict ACID transactions on PostgreSQL would require row-level locking (`SELECT ... FOR UPDATE`) on every redirect, severely degrading throughput.
- Instead, the API seeds an atomic Redis counter `link:{id}:clicks` from PostgreSQL when the cache is loaded. Subsequent redirects increment this counter in Redis (`INCR`). This provides ultra-low latency enforcement while remaining sufficiently accurate for production workloads.

---

## Testing & Code Quality

The test suite runs against a separate, dedicated PostgreSQL database (`TEST_DATABASE_URL`) and uses `fakeredis` for in-memory Redis emulation, ensuring zero test pollution.

### Run Tests with Coverage
```bash
# Activate your virtual environment
source .venv/bin/activate

# Execute pytest with coverage report
pytest --cov=app -v
```

### Measured Test Results
- **Status**: 31 passed in 13.93s
- **Total Coverage**: **88%** measured overall statement coverage.

### Code Style & Linting
Enforced using [Ruff](https://github.com/astral-sh/ruff) with strict checks:
```bash
ruff check .
```

---

## Load Testing with Locust

A realistic Locust load testing suite is included in `locustfile.py`. It simulates a heavy redirect read workload (95% weight) alongside authenticated link generation (5% weight), configured with `allow_redirects=False` to isolate and measure the shortener's own response latency.

### Instructions to Run Load Test

1. Ensure the service is running (`docker compose up -d`).
2. Run Locust with **Cache Enabled** (`CACHE_ENABLED=true`):
   ```bash
   locust -f locustfile.py --host=http://localhost:8000 --headless -u 100 -r 10 --run-time 1m
   ```
3. Run Locust with **Cache Disabled** (`CACHE_ENABLED=false`):
   Set `CACHE_ENABLED=false` in `.env`, restart the API (`docker compose restart api`), and run:
   ```bash
   locust -f locustfile.py --host=http://localhost:8000 --headless -u 100 -r 10 --run-time 1m
   ```

### Benchmark Results Table

| Configuration | Requests per Second | p50 (ms) | p95 (ms) | p99 (ms) | Error Rate (%) |
|---|---|---|---|---|---|
| **Cache Disabled** (`CACHE_ENABLED=false`) | | | | | |
| **Cache Enabled** (`CACHE_ENABLED=true`) | | | | | |

*(Table left empty for student's measured benchmark numbers)*

---

## Deploying to Render

The repository includes a ready-to-deploy Render Blueprint (`render.yaml`) configured for Render's **Free Tier**.

Because Render does not offer a free background worker tier, our architecture runs **both the FastAPI web server and the Celery analytics worker inside a single web container** via [`start.sh`](file:///Users/animeshkumar03/Desktop/URL_shortner/start.sh). On startup, it applies database migrations (`alembic upgrade head`), launches Celery in the background with `--concurrency=1`, and starts Uvicorn with 1 worker, keeping total memory well within Render's 512 MB free RAM ceiling.

> [!WARNING]
> ### Free Tier Limitations & Warnings
> 1. **Web Service Sleep / Cold Starts**: Free web services automatically spin down after ~15 minutes of idle time. The first request after sleeping will trigger a "cold start" taking approximately 50–60 seconds to boot the container.
> 2. **PostgreSQL Expiration (30 Days)**: Render's free PostgreSQL databases expire and are automatically deleted **30 days** after creation.
> 3. **Key Value Ephemeral Nature (No Persistence)**: Render Key Value (free plan) operates strictly in-memory without persistent disk snapshots. Any restarts will flush cached items and queue state (the API safely repopulates link caches from PostgreSQL upon misses).

### Step-by-Step Blueprint Deployment

1. **Fork or Push to GitHub**:
   Ensure your code (including `render.yaml`, `Dockerfile`, and `start.sh`) is committed and pushed to your GitHub repository.

2. **Create a New Blueprint Instance on Render**:
   - Log in to your [Render Dashboard](https://dashboard.render.com/).
   - Click **New +** in the top navigation and select **Blueprint**.
   - Connect your GitHub repository (`URL_Shortener`).
   - Render automatically detects `render.yaml` and parses the resources:
     - **Web Service**: `url-shortener` (Docker runtime, free plan, `/health` check).
     - **PostgreSQL Database**: `url-shortener-db` (free plan).
     - **Key Value Instance**: `url-shortener-kv` (free plan).
   - Render will auto-generate secure 32+ character secrets for `JWT_SECRET` and `IP_HASH_SALT`.
   - Click **Apply** to deploy all components in the same region.

3. **Configure `BASE_URL`**:
   - Once the web service finishes deploying, copy its public URL from the dashboard (e.g. `https://url-shortener-xxxx.onrender.com`).
   - Go to your `url-shortener` Web Service -> **Environment** tab.
   - Set `BASE_URL` to your service URL (`https://url-shortener-xxxx.onrender.com`) and save changes.
   *(Note: The application also includes an automatic fallback to `RENDER_EXTERNAL_URL` if `BASE_URL` is omitted).*

4. **Verify Deployment**:
   - Live URL: [`https://url-shortener-99ta.onrender.com`](https://url-shortener-99ta.onrender.com)
   - Interactive API docs: [`https://url-shortener-99ta.onrender.com/docs`](https://url-shortener-99ta.onrender.com/docs)
   - Health check endpoint: [`https://url-shortener-99ta.onrender.com/health`](https://url-shortener-99ta.onrender.com/health) (returns `{"status":"ok","database":"ok","redis":"ok"}`).

### Optional MaxMind GeoLite2 Setup
To enable geographic city/country tracking in analytics:
1. Register for a free MaxMind account at [dev.maxmind.com](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data).
2. Download `GeoLite2-City.mmdb`.
3. Provide the database file via container volume or build step and set `GEOIP_DB_PATH=/path/to/GeoLite2-City.mmdb`.
4. If omitted, the service functions normally and logs country/city as `NULL`.

---

## Future Improvements

1. **Batched Redis Counter Flush**:
   - Rather than updating PostgreSQL `click_count` on every single Celery click task, buffer click increments in Redis and flush them to PostgreSQL in scheduled micro-batches (e.g. every 10 seconds) using Celery Beat.
2. **Daily Pre-Aggregation Rollup Table**:
   - Create a `daily_link_stats` summary table. A nightly background cron aggregates raw `clicks` into pre-computed daily buckets (`link_id`, `date`, `clicks`, `unique_visitors`), drastically speeding up multi-year timeseries queries.
3. **Monthly Table Partitioning for `clicks`**:
   - For high-volume services (billions of clicks), partition the PostgreSQL `clicks` table by range on `clicked_at` (e.g. `clicks_2026_10`). This bounds index sizes and allows dropping old partitions instantly.
4. **Dedicated Distributed Key Generation Service (KGS)**:
   - For ultra-high concurrent link generation across multiple regions, pre-generate random Base62 tokens offline and load them into a distributed key queue (e.g. using ZooKeeper / Token Vending), eliminating runtime collision retry loops entirely.

# Architectural & Design Decisions

This document records key design decisions, trade-offs, and rationale for interview discussions.

| Decision | Rationale |
|---|---|
| **Max Clicks Approximation** | Enforced approximately using Redis counter `link:{id}:clicks` seeded from database `click_count` on cache fill to avoid hitting PostgreSQL on every redirect while maintaining high throughput. |
| **Direct bcrypt instead of passlib** | `passlib` is unmaintained and incompatible with newer bcrypt/Python releases; direct `bcrypt.hashpw` and `bcrypt.checkpw` are robust, standard, and lightweight. |
| **Plain `def` endpoints with sync SQLAlchemy** | Sync SQLAlchemy sessions in FastAPI standard threadpool endpoints keep code simple, predictable, and straightforward to explain without async ORM subtleties. |
| **7-Character Base62 Short Codes** | $62^7 \approx 3.52$ trillion combinations provide an enormous keyspace with low collision probability, backed by a DB unique constraint and up to 5 retries. |
| **Sliding Window Rate Limiter via Redis Sorted Sets** | Redis sorted sets (`ZREMRANGEBYSCORE`, `ZADD`, `ZCARD`) provide accurate sliding-window rate limiting per IP or user without fixed-window boundary burst vulnerabilities. |
| **Fail-Open Strategy for Redis/Queue Downtime** | If Redis or Celery encounters transient failure during rate check or event enqueueing, the system logs a warning and allows redirects to proceed to maximize availability. |
| **HMAC-SHA256 for IP Addresses** | Raw client IPs are never stored in the database to protect user privacy (GDPR/compliance); IP hashes enable unique visitor counting (`COUNT(DISTINCT ip_hash)`). |
| **Negative Caching (60s)** | Caches nonexistent short codes in Redis for 60 seconds to protect PostgreSQL against cache-penetration denial-of-service attacks. |
| **404 Instead of 403 on Unauthorized Link Access** | Returning 404 for resources owned by other users prevents link enumeration and information leakage. |

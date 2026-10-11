# ruff: noqa: E402
"""Seed knowledge base with runbooks, postmortems, and labeled evaluation queries.

Populates the knowledge_chunks table in PostgreSQL and saves eval/dataset.json with 42 labeled
incident test cases mapping to ground-truth documentation.
"""

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

# Ensure backend is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import AsyncSessionLocal
from app.models.enums import Criticality, IncidentSeverity, IncidentStatus, ServiceStatus
from app.models.incident import Incident
from app.models.postmortem import Postmortem
from app.models.runbook import Runbook
from app.models.service import Service
from app.repositories.knowledge_repo import KnowledgeRepository
from sqlalchemy import select

EVAL_SCENARIOS = [
    {
        "id": "eval-01",
        "service_name": "Auth & Token Service",
        "service_slug": "auth-service",
        "incident_title": "JWT Signature Validation Replay Storm",
        "incident_description": "High rate of expired refresh token replay attempts causing auth rejection spikes and 401 storms.",
        "doc_type": "runbook",
        "doc_title": "Runbook: Auth Service JWT Token Replay and Key Rotation",
        "doc_content": "Auth Service Runbook: When JWT signature validation fails repeatedly or refresh token replay is detected, "
        "immediately revoke compromised tokens in the Redis token blacklist. Verify system clock drift across worker nodes using NTP. "
        "Rotate the RSA signing key in Vault if token tampering is suspected. Execute Redis FLUSHDB on the token revocation namespace "
        "only after verifying identity provider key sync.",
    },
    {
        "id": "eval-02",
        "service_name": "Postgres Database Cluster",
        "service_slug": "postgres-cluster",
        "incident_title": "Postgres Connection Pool Exhaustion max_connections Exceeded",
        "incident_description": "Client applications receiving FATAL: remaining connection slots are reserved for non-replication superuser connections.",
        "doc_type": "runbook",
        "doc_title": "Runbook: Postgres Connection Pool and PgBouncer Saturation",
        "doc_content": "Database Runbook: When PostgreSQL connection pool exceeds max_connections, check pg_stat_activity for idle in transaction "
        "sessions. Terminate blocking idle connections using pg_terminate_backend(pid). Verify PgBouncer connection pooling mode is set to "
        "transaction pooling rather than session pooling. Check microservice connection leak where connections are not returned to pool.",
    },
    {
        "id": "eval-03",
        "service_name": "Payment Gateway API",
        "service_slug": "payment-api",
        "incident_title": "Stripe Webhook Signature Verification Clock Skew Failure",
        "incident_description": "Incoming Stripe payment webhooks failing HMAC signature verification with timestamp outside tolerance window.",
        "doc_type": "postmortem",
        "doc_title": "Postmortem: Stripe Webhook Rejection Outage",
        "doc_content": "Payment API Postmortem: Webhooks were rejected due to a 350-second clock skew between payment gateway EC2 instances and Stripe. "
        "Stripe webhook tolerance is 300 seconds. Resolution: Synchronized chrony daemon with Amazon Time Sync Service (169.254.169.123). "
        "Root cause was AWS hypervisor clock drift on older instance types. Action items include Prometheus alert for clock_offset_seconds > 5.",
    },
    {
        "id": "eval-04",
        "service_name": "Order Processing Service",
        "service_slug": "order-service",
        "incident_title": "Kafka Consumer Group Rebalance Storm on Partition Lag",
        "incident_description": "Order consumers repeatedly dropping out of consumer group due to max.poll.interval.ms timeout during database slow queries.",
        "doc_type": "runbook",
        "doc_title": "Runbook: Kafka Consumer Lag and Rebalance Storms",
        "doc_content": "Order Service Runbook: When Kafka consumers enter continuous rebalancing loops, inspect max.poll.interval.ms vs message processing time. "
        "If orders take longer than 300s to process due to slow downstream inventory locks, increase max.poll.interval.ms to 600s or reduce max.poll.records to 50. "
        "Check Kafka partition distribution and verify consumer heartbeat thread is not starved of CPU.",
    },
    {
        "id": "eval-05",
        "service_name": "Redis Distributed Cache",
        "service_slug": "redis-cache",
        "incident_title": "Redis Eviction Storm and Memory Pressure Under Allkeys-LRU",
        "incident_description": "Redis memory reaching maxmemory limit, eviction count skyrocketing, latency spiking from sub-millisecond to 120ms.",
        "doc_type": "runbook",
        "doc_title": "Runbook: Redis Maxmemory and Eviction Latency Degradation",
        "doc_content": "Redis Runbook: When Redis evicted_keys spikes and used_memory approaches maxmemory, identify large keys using redis-cli --bigkeys. "
        "Inspect if TTL was omitted on session caching keys or analytics payload buffers. Temporarily scale Redis instance memory or adjust "
        "maxmemory-policy to volatile-lru if persistent keys must not be evicted. Implement key compression for payloads exceeding 10KB.",
    },
    {
        "id": "eval-06",
        "service_name": "Search & Indexing Engine",
        "service_slug": "search-engine",
        "incident_title": "Elasticsearch Unassigned Shards and Red Cluster State",
        "incident_description": "Elasticsearch cluster state RED due to disk watermark exceeded on data nodes, blocking search and indexing operations.",
        "doc_type": "runbook",
        "doc_title": "Runbook: Elasticsearch Red Cluster Disk Watermark Recovery",
        "doc_content": "Search Engine Runbook: When cluster state is RED with unassigned primary shards, check GET _cluster/allocation/explain. "
        "If disk watermark high (90%) or flood_stage (95%) is breached, index.blocks.read_only_allow_delete is enforced. "
        "Delete obsolete indices, expand EBS volume storage, and reset read-only block using index.blocks.read_only_allow_delete: null.",
    },
    {
        "id": "eval-07",
        "service_name": "Kubernetes Ingress Controller",
        "service_slug": "ingress-controller",
        "incident_title": "NGINX Ingress 504 Gateway Timeout Cascade",
        "incident_description": "Client traffic receiving 504 Gateway Timeout on checkout and cart endpoints while ingress CPU remains below 40%.",
        "doc_type": "postmortem",
        "doc_title": "Postmortem: NGINX Ingress 504 Upstream Connection Keepalive Exhaustion",
        "doc_content": "Ingress Postmortem: Ingress proxies threw 504 Gateway Timeouts because upstream backend services exhausted their internal thread pools. "
        "Proxy timeout was configured to 60s, but upstream database queries hung on lock acquisition. Resolution: Enabled aggressive circuit breakers "
        "with Envoy and lowered proxy_read_timeout to 10s to fail fast. Configured upstream keepalive connection pools to prevent socket churn.",
    },
    {
        "id": "eval-08",
        "service_name": "Inventory Catalog Service",
        "service_slug": "inventory-service",
        "incident_title": "PostgreSQL Row Lock Contention on Hot SKU Stock Decrement",
        "incident_description": "High transaction rollback rate and latency spike to 4500ms on flash sale checkout updating single SKU quantity.",
        "doc_type": "runbook",
        "doc_title": "Runbook: Inventory Stock Row Lock Contention and Deadlock Resolution",
        "doc_content": "Inventory Runbook: Concurrent SELECT FOR UPDATE on single inventory rows during flash sales causes severe row lock contention and deadlocks. "
        "Mitigation: Implement inventory batch reservation in Redis using atomic Lua DECRBY before committing to PostgreSQL. "
        "Ensure queries sort SKU IDs deterministically before locking to eliminate circular deadlock conditions. Monitor pg_locks for ExclusiveLock.",
    },
    {
        "id": "eval-09",
        "service_name": "API Gateway Core",
        "service_slug": "api-gateway",
        "incident_title": "Rate Limiting Starvation and 429 Cascades on Internal RPC",
        "incident_description": "Internal microservices receiving 429 Too Many Requests from API Gateway rate limiter after upstream IP spoofing.",
        "doc_type": "runbook",
        "doc_title": "Runbook: API Gateway Sliding Window Rate Limiting and Token Bucket",
        "doc_content": "API Gateway Runbook: If internal services get throttled with 429 Too Many Requests, verify if the rate limit key is evaluating "
        "the internal proxy IP rather than the true client IP. Inspect X-Forwarded-For headers and trusted_proxies configuration in Gateway settings. "
        "Emergency bypass: Add service IAM token to rate_limit_whitelist in Redis configuration.",
    },
    {
        "id": "eval-10",
        "service_name": "Notification Dispatcher",
        "service_slug": "notification-service",
        "incident_title": "SendGrid Email Dispatch Rate Limit and Queue Backlog",
        "incident_description": "Outbound email delivery queue exceeding 150,000 pending tasks with SendGrid returning 429 Too Many Requests.",
        "doc_type": "runbook",
        "doc_title": "Runbook: SendGrid Rate Limiting and Asynchronous Email Retry Backoff",
        "doc_content": "Notification Runbook: SendGrid enforces API rate limits per second. When 429 is encountered, Celery tasks must apply exponential backoff "
        "with jitter rather than immediate retry. Reroute transactional security alerts (password reset, 2FA) to fallback provider Amazon SES. "
        "Pause marketing campaigns in Redis queue to prioritize priority transactional emails.",
    },
    {
        "id": "eval-11",
        "service_name": "User Profile Service",
        "service_slug": "user-service",
        "incident_title": "Argon2id CPU Starvation on Bulk User Password Verification",
        "incident_description": "Kubernetes pods hitting 100% CPU limits due to batch login attempts invoking resource-intensive Argon2id password hashing.",
        "doc_type": "runbook",
        "doc_title": "Runbook: Password Hashing Argon2id Resource Limits and Throttling",
        "doc_content": "User Service Runbook: Argon2id is intentionally memory and CPU intensive (time_cost=3, memory_cost=65536). "
        "Under credential stuffing attacks, pod CPUs saturate rapidly. Immediate mitigation: Enable Cloudflare bot challenge and enforce "
        "per-IP sliding window rate limiting on /api/v1/auth/login. Scale user-service pod HPA to 10 replicas.",
    },
    {
        "id": "eval-12",
        "service_name": "File Storage Subsystem",
        "service_slug": "storage-service",
        "incident_title": "S3 503 Slow Down Request Rate Exceeded on Single Prefix",
        "incident_description": "Asset upload pipeline throwing botocore 503 Slow Down errors when saving customer invoice PDFs.",
        "doc_type": "postmortem",
        "doc_title": "Postmortem: Amazon S3 503 Slow Down Outage on Monolithic S3 Prefix",
        "doc_content": "Storage Postmortem: S3 partitions support up to 3,500 PUT/LIST and 5,500 GET requests per second per prefix. "
        "All invoices were being written directly to /invoices/YYYY-MM-DD/ resulting in partition throttling. "
        "Fix: Introduced hex hash prefixes (/invoices/{hash[:4]}/YYYY-MM-DD/) to distribute requests across distinct S3 partition keys.",
    },
    {
        "id": "eval-13",
        "service_name": "Background Worker Cluster",
        "service_slug": "worker-service",
        "incident_title": "Celery Worker OOMKilled Exit Code 137 on Large Report Generation",
        "incident_description": "Worker pods terminating with exit code 137 (SIGKILL) while parsing multi-gigabyte CSV exports.",
        "doc_type": "runbook",
        "doc_title": "Runbook: Celery Worker Memory Leaks and OOMKilled Exit Code 137",
        "doc_content": "Worker Runbook: When Celery worker processes get OOMKilled by Linux kernel cgroup, inspect task payload sizes. "
        "Ensure CSV export generation streams rows using server-side database cursors rather than loading entire datasets into pandas DataFrame memory. "
        "Configure worker_max_tasks_per_child = 50 to periodically recycle Python processes and prevent memory fragmentation.",
    },
    {
        "id": "eval-14",
        "service_name": "Kubernetes Cluster Core",
        "service_slug": "k8s-cluster",
        "incident_title": "Pod CrashLoopBackOff Due to Missing ConfigMap Secret Key",
        "incident_description": "Pods failing readiness and liveness probes immediately upon startup with CreateContainerConfigError.",
        "doc_type": "runbook",
        "doc_title": "Runbook: Kubernetes CrashLoopBackOff and Missing Secret Keys",
        "doc_content": "Kubernetes Runbook: Pods reporting CrashLoopBackOff or CreateContainerConfigError indicate missing environment variables "
        "from Kubernetes Secrets or ConfigMaps. Run kubectl describe pod <pod_name> to verify which key is unresolved. "
        "Verify ExternalSecrets operator synced the Vault secret. Restart the deployment using kubectl rollout restart.",
    },
    {
        "id": "eval-15",
        "service_name": "DNS and Routing Service",
        "service_slug": "dns-service",
        "incident_title": "CoreDNS Query Timeout and NXDOMAIN Errors Under Peak Load",
        "incident_description": "Inter-service RPCs intermittently failing with dns resolution timeout and lookup nxdomain.",
        "doc_type": "postmortem",
        "doc_title": "Postmortem: CoreDNS UDP Packet Drop Under High Concurrency",
        "doc_content": "DNS Postmortem: High concurrent DNS lookups caused Linux kernel conntrack table saturation and CoreDNS UDP buffer drops. "
        "Resolution: Deployed NodeLocal DNSCache daemonset to handle DNS caching directly on node loopback interfaces. "
        "Updated glibc ndots:5 configuration to ndots:2 in pod dnsConfig to eliminate redundant recursive search path queries.",
    },
    {
        "id": "eval-16",
        "service_name": "Billing & Subscription Engine",
        "service_slug": "billing-service",
        "incident_title": "Duplicate Invoicing Caused by Missing Idempotency Key",
        "incident_description": "Customers charged twice on network retry during checkout when payment endpoint was invoked multiple times.",
        "doc_type": "runbook",
        "doc_title": "Runbook: Idempotency Key Validation and Replay Protection",
        "doc_content": "Billing Runbook: When duplicate charges are reported, verify client Idempotency-Key header transmission. "
        "Our billing service stores SHA-256 hashes of idempotency keys in PostgreSQL table idempotency_keys with unique constraints. "
        "Ensure API endpoints verify idempotency key existence and return cached 200 responses rather than re-executing credit card charges.",
    },
    {
        "id": "eval-17",
        "service_name": "Message Broker RabbitMQ",
        "service_slug": "rabbitmq-broker",
        "incident_title": "RabbitMQ Unacknowledged Message Memory Alarm Blocking Producers",
        "incident_description": "RabbitMQ blocking socket connections from publishers due to vm_memory_high_watermark alarm triggered.",
        "doc_type": "runbook",
        "doc_title": "Runbook: RabbitMQ Memory High Watermark and Unacked Message Piles",
        "doc_content": "RabbitMQ Runbook: When RabbitMQ triggers memory alarm, publisher channels are blocked. Check rabbitmqctl list_queues "
        "for unacknowledged message counts. If consumer prefetch_count is too large, unacked messages consume broker RAM. "
        "Lower prefetch_count to 50 on consumer workers. Purge dead letter queues if poison pill messages are looping.",
    },
    {
        "id": "eval-18",
        "service_name": "Postgres Database Cluster",
        "service_slug": "postgres-cluster",
        "incident_title": "PostgreSQL Table Bloat and Autovacuum Freeze Lag",
        "incident_description": "Alert: transaction ID wraparound impending, autovacuum failing to complete on high-write incident_events table.",
        "doc_type": "runbook",
        "doc_title": "Runbook: Postgres Table Bloat, Dead Tuples, and Autovacuum Tuning",
        "doc_content": "PostgreSQL Runbook: When autovacuum cannot keep pace with DELETE/UPDATE dead tuples, query pg_stat_user_tables for n_dead_tup. "
        "Long-running transactions hold backxmin, preventing vacuum from reclaiming dead tuples. Terminate queries running > 1 hour. "
        "Tune autovacuum_vacuum_cost_limit to 1000 and run VACUUM (ANALYZE, VERBOSE) during off-peak hours.",
    },
    {
        "id": "eval-19",
        "service_name": "Security & SSL Infrastructure",
        "service_slug": "ssl-infrastructure",
        "incident_title": "TLS Leaf Certificate Expiration Handshake Failure",
        "incident_description": "Clients receiving SEC_ERROR_EXPIRED_CERTIFICATE on api.domain.com during SSL negotiation.",
        "doc_type": "runbook",
        "doc_title": "Runbook: Emergency TLS Certificate Renewal with Let's Encrypt and cert-manager",
        "doc_content": "Security Runbook: In the event of an expired TLS leaf certificate, check cert-manager ingress logs for ACME HTTP01 challenge failures. "
        "If challenge was blocked by WAF firewall rules, whitelist /.well-known/acme-challenge/. Manually renew certificate using "
        "cmctl renew <cert-name> or import emergency DigiCert wild-card certificate into Kubernetes tls-secret.",
    },
    {
        "id": "eval-20",
        "service_name": "WebSocket Notification Hub",
        "service_slug": "websocket-hub",
        "incident_title": "WebSocket Connection Dropping Storm on AWS ALB Idle Timeout",
        "incident_description": "Thousands of active browser clients disconnecting simultaneously every 60 seconds and reconnecting in thundering herd.",
        "doc_type": "postmortem",
        "doc_title": "Postmortem: WebSocket Thundering Herd on ALB 60s Idle Timeout",
        "doc_content": "WebSocket Postmortem: AWS Application Load Balancer closed idle TCP connections after 60 seconds because frontend did not "
        "send application-level ping/pong heartbeats. 50,000 clients simultaneously reconnected, saturating backend auth servers. "
        "Fix: Configured client-side ping every 25 seconds and increased ALB idle timeout to 300 seconds. Added jitter to reconnect backoff.",
    },
    {
        "id": "eval-21",
        "service_name": "Search & Indexing Engine",
        "service_slug": "search-engine",
        "incident_title": "Full-Text Search tsvector GIN Index Degradation",
        "incident_description": "Incident log search query latency spiking from 15ms to 1200ms following massive 500,000 log row ingestion.",
        "doc_type": "runbook",
        "doc_title": "Runbook: PostgreSQL GIN Index Fastupdate and Vacuum Maintenance",
        "doc_content": "Search Runbook: High-rate inserts into PostgreSQL tables with GIN indexes causes the pending list (fastupdate) to grow excessively, "
        "degrading read performance. Solution: Execute SELECT gin_clean_pending_list('idx_log_entries_search_vector'). "
        "Verify maintenance_work_mem is at least 512MB to speed up GIN index vacuuming.",
    },
    {
        "id": "eval-22",
        "service_name": "Auth & Token Service",
        "service_slug": "auth-service",
        "incident_title": "Distributed Session Desynchronization on Redis Pub/Sub Outage",
        "incident_description": "User logout events not propagating across cluster nodes, allowing invalidated JWT tokens to remain active on other instances.",
        "doc_type": "runbook",
        "doc_title": "Runbook: Redis Pub/Sub WebSocket and Session Invalidation Fanout",
        "doc_content": "Auth Runbook: Session invalidation and live alerts rely on Redis Pub/Sub channel 'incident_events'. If Redis connection drops, "
        "backend workers fail to broadcast token revocations. Verify Redis client reconnect backoff and healthcheck probes. "
        "Clients should poll /api/v1/auth/session status as a fallback when WebSocket connection is down.",
    },
    {
        "id": "eval-23",
        "service_name": "Order Processing Service",
        "service_slug": "order-service",
        "incident_title": "Order Processing Deadlock on Cross-Table Update Order",
        "incident_description": "Concurrent order payment and warehouse allocation transactions aborting with deadlock detected error in PostgreSQL.",
        "doc_type": "postmortem",
        "doc_title": "Postmortem: Inconsistent Lock Acquisition Order Causing Deadlocks",
        "doc_content": "Order Postmortem: Two services locked orders and shipments in opposite order: Service A locked order then shipment; "
        "Service B locked shipment then order. High concurrency caused reciprocal lock waits. Resolution: Enforced global ordering "
        "convention: always lock orders before shipments. Wrapped critical updates in SELECT FOR UPDATE in strict ascending ID order.",
    },
    {
        "id": "eval-24",
        "service_name": "Payment Gateway API",
        "service_slug": "payment-api",
        "incident_title": "External Provider Gateway 502 Bad Gateway Spike",
        "incident_description": "Third-party payment processor throwing 502 Bad Gateway during seasonal traffic surge.",
        "doc_type": "runbook",
        "doc_title": "Runbook: Third-Party Payment Gateway Circuit Breakers and Fallback",
        "doc_content": "Payment API Runbook: If upstream payment processor returns 502/503 errors, do not continuously hammer their endpoint. "
        "Engage circuit breaker to open state when error rate exceeds 20% over 60 seconds. Reroute eligible card transactions to secondary "
        "payment processor Adyen. Notify customer with friendly retry notification rather than generic server error.",
    },
    {
        "id": "eval-25",
        "service_name": "Background Worker Cluster",
        "service_slug": "worker-service",
        "incident_title": "Celery Beat Scheduler Stalling Cron Healthcheck Probes",
        "incident_description": "Periodic healthchecks stopped executing, celery beat process unresponsive in single-threaded loop.",
        "doc_type": "runbook",
        "doc_title": "Runbook: Celery Beat Schedule File Corruption and Clock Sync",
        "doc_content": "Worker Runbook: When Celery Beat stops dispatching scheduled cron tasks, check celerybeat-schedule database file. "
        "If process crashed during write, the shelf file can become corrupted. Delete celerybeat-schedule and restart beat worker. "
        "Verify system time is synchronized with UTC and Celery timezone is set to settings.CELERY_TIMEZONE = 'UTC'.",
    },
    {
        "id": "eval-26",
        "service_name": "Kubernetes Ingress Controller",
        "service_slug": "ingress-controller",
        "incident_title": "Linux File Descriptor EMFILE Too Many Open Files",
        "incident_description": "Ingress controller failing new socket connections with socket() failed (24: Too many open files).",
        "doc_type": "runbook",
        "doc_title": "Runbook: Operating System File Descriptor Limits and Socket Leaks",
        "doc_content": "Ingress Runbook: When processes throw EMFILE (Too many open files), inspect /proc/sys/fs/file-nr and ulimit -n. "
        "In Kubernetes pod security context, set sysctls and securityContext.capabilities to allow rlimit nofile = 65536. "
        "Inspect connection pool settings in Python/Go apps to ensure HTTP clients close idle connections in response body finally blocks.",
    },
    {
        "id": "eval-27",
        "service_name": "Postgres Database Cluster",
        "service_slug": "postgres-cluster",
        "incident_title": "Postgres Streaming Replication Lag Exceeding 500 Megabytes",
        "incident_description": "Read replica lag increasing continuously, readers serving stale data during heavy database write batch.",
        "doc_type": "runbook",
        "doc_title": "Runbook: Postgres WAL Sender and Streaming Replication Lag",
        "doc_content": "Postgres Runbook: Replication lag on read replicas occurs when write volume on primary exceeds replica WAL replay rate. "
        "Query pg_stat_replication for write_lag, flush_lag, and replay_lag. If replica is bottlenecked on I/O, enable hot_standby_feedback = on "
        "and scale replica disk throughput. Check if long-running analytical queries on replica are conflicting with incoming WAL recovery.",
    },
    {
        "id": "eval-28",
        "service_name": "File Storage Subsystem",
        "service_slug": "storage-service",
        "incident_title": "Disk Inode Exhaustion Despite 70% Free Disk Space",
        "incident_description": "Application throwing No space left on device when writing logs, despite df -h showing 250GB available.",
        "doc_type": "postmortem",
        "doc_title": "Postmortem: Inode Starvation Caused by Millions of Unpurged Temporary Files",
        "doc_content": "Storage Postmortem: Applications could not write files because the filesystem inode table was 100% full (df -i showed 0 inodes free). "
        "Root cause: A runaway PDF generator created millions of 0-byte temporary files in /tmp/render/ without cleaning them up. "
        "Resolution: Removed orphaned files using find /tmp/render -type f -delete and added daily systemd tmpfiles-clean service.",
    },
    {
        "id": "eval-29",
        "service_name": "Notification Dispatcher",
        "service_slug": "notification-service",
        "incident_title": "Twilio SMS Delivery Webhook Queue Flood",
        "incident_description": "Twilio SMS status callback webhooks overwhelming notification worker pods, causing 503 Service Unavailable.",
        "doc_type": "runbook",
        "doc_title": "Runbook: Webhook Ingestion Buffer and Kafka Decoupling",
        "doc_content": "Notification Runbook: Never process webhook business logic synchronously in the HTTP request handler. "
        "Immediately write raw webhook payloads to Kafka or RabbitMQ with an HTTP 202 Accepted response. "
        "If webhook consumers lag, scale Kafka partition consumer group instances rather than throttling incoming provider webhooks.",
    },
    {
        "id": "eval-30",
        "service_name": "Inventory Catalog Service",
        "service_slug": "inventory-service",
        "incident_title": "Redis Cache Stampede on Catalog Master Key Expiration",
        "incident_description": "All backend instances hitting PostgreSQL simultaneously for product catalog upon TTL expiration, spiking DB CPU to 100%.",
        "doc_type": "postmortem",
        "doc_title": "Postmortem: Cache Stampede (Dogpiling) on High-Traffic Catalog Key",
        "doc_content": "Inventory Postmortem: When catalog:featured key expired, 800 concurrent requests experienced cache misses and executed heavy "
        "joins on PostgreSQL simultaneously. Resolution: Implemented Probabilistic Early Expiration (XFetch algorithm) and distributed mutex locking "
        "using Redis Redlock so only one worker refreshes the cache while others serve stale data gracefully.",
    },
    {
        "id": "eval-31",
        "service_name": "API Gateway Core",
        "service_slug": "api-gateway",
        "incident_title": "CORS Preflight Options Request Overhead Saturation",
        "incident_description": "Browser OPTIONS preflight requests accounting for 60% of total API Gateway traffic, degrading edge latency.",
        "doc_type": "runbook",
        "doc_title": "Runbook: CORS Access-Control-Max-Age Optimization",
        "doc_content": "API Gateway Runbook: If OPTIONS preflight requests overload API Gateway, inspect Access-Control-Max-Age header. "
        "By default, browsers without max-age send an OPTIONS request before every POST/PUT/DELETE. "
        "Configure Gateway CORS middleware to return Access-Control-Max-Age: 86400 (24 hours) to instruct browsers to cache preflight decisions.",
    },
    {
        "id": "eval-32",
        "service_name": "Security & SSL Infrastructure",
        "service_slug": "ssl-infrastructure",
        "incident_title": "AWS IAM Instance Role Credential Expiration During Auto-Deployment",
        "incident_description": "CI/CD deployment runner failing with botocore ClientError: The security token included in the request is expired.",
        "doc_type": "runbook",
        "doc_title": "Runbook: AWS STS AssumeRole Token Lifetimes and OIDC Federation",
        "doc_content": "Security Runbook: When AWS deployments fail with expired security token errors, inspect GitHub Actions OIDC role duration. "
        "By default, STS AssumeRole tokens expire after 3600 seconds (1 hour). For long-running migrations and seed scripts, "
        "request DurationSeconds: 14400 (4 hours) on the IAM role or refresh credentials dynamically before executing database migrations.",
    },
    {
        "id": "eval-33",
        "service_name": "Search & Indexing Engine",
        "service_slug": "search-engine",
        "incident_title": "HNSW Vector Index Cosine Distance Metric Inconsistency",
        "incident_description": "Semantic vector search returning irrelevant results when vectors are unnormalized under vector_cosine_ops.",
        "doc_type": "postmortem",
        "doc_title": "Postmortem: Vector Normalization and pgvector HNSW Index Configuration",
        "doc_content": "Search Postmortem: Embeddings inserted into pgvector knowledge_chunks had variable magnitudes, causing cosine distance "
        "calculations to skew towards longer text chunks. Fix: Enforced unit L2 normalization (sum of squares = 1.0) on all embeddings "
        "prior to insertion in KnowledgeRepository. Created HNSW index with m=16, ef_construction=64 using vector_cosine_ops.",
    },
    {
        "id": "eval-34",
        "service_name": "User Profile Service",
        "service_slug": "user-service",
        "incident_title": "User Account Enumeration Vulnerability on Password Reset",
        "incident_description": "Security audit finding: Response timing discrepancy on /api/v1/auth/forgot-password reveals valid vs invalid emails.",
        "doc_type": "runbook",
        "doc_title": "Runbook: Constant-Time Responses and Timing Attack Mitigation",
        "doc_content": "User Service Runbook: When handling password reset requests, ensure the endpoint executes in constant time regardless of "
        "whether the email exists in the database. Always return generic HTTP 200 'If an account exists, an email has been sent'. "
        "If account is not found, execute a dummy Argon2 hash computation to prevent side-channel timing analysis.",
    },
    {
        "id": "eval-35",
        "service_name": "Billing & Subscription Engine",
        "service_slug": "billing-service",
        "incident_title": "Floating-Point Rounding Error in Currency Tax Calculation",
        "incident_description": "Financial reconciliation discrepancy of $0.01 on multi-item enterprise invoices due to IEEE 754 float arithmetic.",
        "doc_type": "postmortem",
        "doc_title": "Postmortem: IEEE 754 Floating-Point Precision Loss in Financial Transactions",
        "doc_content": "Billing Postmortem: Invoice calculation used standard Python float types, resulting in 0.1 + 0.2 = 0.30000000000000004. "
        "Over 100,000 transactions, micro-rounding errors accumulated into accounting discrepancies. Resolution: Migrated all monetary columns "
        "in PostgreSQL to NUMERIC(12, 4) and converted all Python calculations to use decimal.Decimal with ROUND_HALF_EVEN rounding.",
    },
    {
        "id": "eval-36",
        "service_name": "Kubernetes Cluster Core",
        "service_slug": "k8s-cluster",
        "incident_title": "Kubernetes Node Disk Pressure and Image Eviction",
        "incident_description": "Cluster nodes marked NotReady with KubeletHasDiskPressure, pods getting evicted across multiple namespaces.",
        "doc_type": "runbook",
        "doc_title": "Runbook: Kubelet Disk Pressure, Containerd Image Pruning, and Log Rotation",
        "doc_content": "Kubernetes Runbook: When kubelet reports DiskPressure, containerd image garbage collection activates. "
        "Check /var/lib/containerd and /var/log/pods for runaway docker container logs. Verify logrotate is configured with maxsize 50M. "
        "Execute crictl rmi --prune to reclaim unreferenced container images.",
    },
    {
        "id": "eval-37",
        "service_name": "DNS and Routing Service",
        "service_slug": "dns-service",
        "incident_title": "BGP Route Flapping Upstream Transit Provider Packet Loss",
        "incident_description": "Intermittent 15% packet loss on external traffic routed through primary Tier 1 ISP transit provider.",
        "doc_type": "runbook",
        "doc_title": "Runbook: BGP Route Dampening and Multi-Homed ISP Failover",
        "doc_content": "Network Runbook: If upstream ISP experiences BGP route flapping, border routers flap routes, dropping TCP connections. "
        "Check BGP session state using show ip bgp summary. Manually prepend AS path or withdraw routes on flapped provider interface "
        "to shift all transit traffic to secondary carrier Level3/Lumen. Enable BGP route flap dampening.",
    },
    {
        "id": "eval-38",
        "service_name": "Redis Distributed Cache",
        "service_slug": "redis-cache",
        "incident_title": "Redis Sentinel Failover Split-Brain Configuration Desync",
        "incident_description": "Application nodes writing to former Redis master while sentinel promoted new master during network partition.",
        "doc_type": "postmortem",
        "doc_title": "Postmortem: Redis Sentinel Split-Brain on Incomplete Min-Replicas-To-Write",
        "doc_content": "Redis Postmortem: During network partition, old master continued accepting writes that were subsequently overwritten "
        "when sentinel promoted new replica. Fix: Configured min-replicas-to-write 1 and min-replicas-max-lag 10 on all Redis instances. "
        "This prevents a partitioned master from accepting writes if it cannot communicate with at least one replica.",
    },
    {
        "id": "eval-39",
        "service_name": "Message Broker RabbitMQ",
        "service_slug": "rabbitmq-broker",
        "incident_title": "RabbitMQ Poison Pill Message Infinite Requeue Loop",
        "incident_description": "Consumer crashing with JSONDecodeError, message requeued automatically, crashing consumer loop at 1000 iter/sec.",
        "doc_type": "runbook",
        "doc_title": "Runbook: RabbitMQ Dead Letter Exchanges (DLX) and Poison Pill Handling",
        "doc_content": "RabbitMQ Runbook: Unhandled consumer exceptions that trigger basic_nack(requeue=True) cause poison pill infinite loops. "
        "Configure queues with x-dead-letter-exchange and set x-delivery-limit: 3 using RabbitMQ Quorum Queues. "
        "Consumers must catch DeserializationError, log the corrupted payload to S3, and acknowledge the message to remove it from active queue.",
    },
    {
        "id": "eval-40",
        "service_name": "WebSocket Notification Hub",
        "service_slug": "websocket-hub",
        "incident_title": "Asyncio Event Loop Blocking on Synchronous Requests Call",
        "incident_description": "FastAPI WebSocket server freezing every 30 seconds for 5000ms, causing clients to drop connection.",
        "doc_type": "postmortem",
        "doc_title": "Postmortem: Synchronous requests.get Inside Async Endpoint Freezing Event Loop",
        "doc_content": "WebSocket Postmortem: A developer added requests.get('https://external.api') inside an async WebSocket handler. "
        "Because requests is blocking and synchronous, it stalled Python's single asyncio event loop for all concurrent WebSockets. "
        "Resolution: Replaced requests with httpx.AsyncClient() using async with, and added ruff rule A001 prohibiting synchronous IO in async def.",
    },
    {
        "id": "eval-41",
        "service_name": "Security & SSL Infrastructure",
        "service_slug": "ssl-infrastructure",
        "incident_title": "JWT Algorithm None Header Signature Bypass Attempt",
        "incident_description": "WAF detecting malicious Authorization headers containing alg: none in JWT token header.",
        "doc_type": "runbook",
        "doc_title": "Runbook: JWT Algorithm Whitelisting and Cryptographic Verification",
        "doc_content": "Security Runbook: In JWT verification, attackers may tamper with header {'alg': 'none'} to bypass signature verification. "
        "Ensure PyJWT or python-jose is configured with algorithms=['HS256'] explicitly, never allowing algorithm inference. "
        "Verify tokens reject empty signatures and reject symmetric keys when asymmetric RSA public keys are expected.",
    },
    {
        "id": "eval-42",
        "service_name": "Search & Indexing Engine",
        "service_slug": "search-engine",
        "incident_title": "Elasticsearch Deep Paging OutOfMemoryError on from+size Query",
        "incident_description": "Elasticsearch data node throwing java.lang.OutOfMemoryError when user requested page 50,000 of search results.",
        "doc_type": "runbook",
        "doc_title": "Runbook: Elasticsearch Search-After and Point-In-Time (PIT) Pagination",
        "doc_content": "Search Engine Runbook: Using from: 50000 and size: 20 forces Elasticsearch to coordinate and sort 50,020 documents "
        "across all shards in memory, triggering index.max_result_window (default 10,000) breaches and node OOM. "
        "Resolution: Enforce search_after with Point In Time (PIT) API for deep pagination, or restrict UI search pagination to top 1,000 records.",
    },
]


async def seed_knowledge_base():
    """Seeds the database with services, runbooks, postmortems, and indexed chunks."""
    eval_dir = BASE_DIR / "eval"
    eval_dir.mkdir(parents=True, exist_ok=True)
    dataset_file = eval_dir / "dataset.json"

    labeled_dataset = []

    async with AsyncSessionLocal() as session:
        # Check / create services
        service_map: dict[str, Service] = {}
        for scenario in EVAL_SCENARIOS:
            slug = scenario["service_slug"]
            if slug in service_map:
                continue

            svc = await session.scalar(select(Service).where(Service.slug == slug))
            if not svc:
                svc = Service(
                    name=scenario["service_name"],
                    slug=slug,
                    status=ServiceStatus.HEALTHY,
                    criticality=Criticality.HIGH,
                )
                session.add(svc)
                await session.flush()
            service_map[slug] = svc

        # Seed Runbooks / Postmortems and index them as KnowledgeChunks
        for scenario in EVAL_SCENARIOS:
            svc = service_map[scenario["service_slug"]]
            doc_type = scenario["doc_type"]
            doc_id = uuid4()

            if doc_type == "runbook":
                doc = Runbook(
                    id=doc_id,
                    service_id=svc.id,
                    title=scenario["doc_title"],
                    incident_type="infrastructure",
                    body=scenario["doc_content"],
                )
                session.add(doc)
            else:
                det = datetime.now(UTC)
                inc = Incident(
                    service_id=svc.id,
                    title=scenario["incident_title"],
                    description=scenario["incident_description"],
                    status=IncidentStatus.RESOLVED,
                    severity=IncidentSeverity.SEV2,
                    created_at=det,
                    detected_at=det,
                    acknowledged_at=det + timedelta(minutes=5),
                    resolved_at=det + timedelta(minutes=30),
                )
                session.add(inc)
                await session.flush()

                doc = Postmortem(
                    id=doc_id,
                    incident_id=inc.id,
                    summary=scenario["doc_title"],
                    impact="Elevated latency and degraded customer transactions.",
                    timeline="T+0 detected, T+15 mitigated, T+30 resolved.",
                    root_cause=scenario["doc_content"][:300],
                    resolution=scenario["doc_content"],
                    lessons_learned="Review automated alerting and monitoring thresholds.",
                    preventive_actions="Add alert for metric threshold breach.",
                )
                session.add(doc)

            await session.flush()

            # Index document into KnowledgeRepository
            chunks = await KnowledgeRepository.index_document(
                session=session,
                source_type=doc_type,
                source_id=doc_id,
                service_id=svc.id,
                content=scenario["doc_content"],
            )

            chunk_ids = [str(c.id) for c in chunks]

            labeled_dataset.append(
                {
                    "query_id": scenario["id"],
                    "service_slug": scenario["service_slug"],
                    "service_id": str(svc.id),
                    "service_name": scenario["service_name"],
                    "incident_title": scenario["incident_title"],
                    "incident_description": scenario["incident_description"],
                    "query_text": f"{scenario['incident_title']} {scenario['incident_description']}",
                    "ground_truth_doc_type": doc_type,
                    "ground_truth_doc_id": str(doc_id),
                    "ground_truth_chunk_ids": chunk_ids,
                }
            )

        await session.commit()

    # Save dataset.json
    with open(dataset_file, "w", encoding="utf-8") as f:
        json.dump(labeled_dataset, f, indent=2)

    print(
        f"Successfully seeded {len(EVAL_SCENARIOS)} scenarios into knowledge_chunks and saved {dataset_file}"
    )


if __name__ == "__main__":
    asyncio.run(seed_knowledge_base())

"""Runs EXPLAIN (ANALYZE, BUFFERS) on 3 queries before and after index optimization

on the 100,000 synthetic logs and 2,000 synthetic incidents dataset.
"""

import asyncio

from sqlalchemy import text

from app.core.database import AsyncSessionLocal


async def run_benchmarks() -> dict:
    async with AsyncSessionLocal() as session:
        # Get an active service ID from the seeded database
        svc_row = (await session.execute(text("SELECT id FROM services LIMIT 1;"))).mappings().one()
        svc_id = str(svc_row["id"])

        results = {}

        # ---------------------------------------------------------
        # Query 1: Full-Text Log Search
        # ---------------------------------------------------------
        q1_sql = """
        SELECT id, service_name, level, message, timestamp
        FROM log_entries
        WHERE search_vector @@ to_tsquery('english', 'database | timeout')
        ORDER BY timestamp DESC
        LIMIT 50;
        """
        # BEFORE (force sequential scan)
        await session.execute(text("SET enable_bitmapscan = off;"))
        await session.execute(text("SET enable_indexscan = off;"))
        res1_before = (
            (await session.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {q1_sql}"))).scalars().all()
        )
        # AFTER (enable GIN index scan)
        await session.execute(text("SET enable_bitmapscan = on;"))
        await session.execute(text("SET enable_indexscan = on;"))
        res1_after = (
            (await session.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {q1_sql}"))).scalars().all()
        )

        results["q1_before"] = "\n".join(res1_before)
        results["q1_after"] = "\n".join(res1_after)

        # ---------------------------------------------------------
        # Query 2: MTTR and P95 Calculation Filtered by Service
        # ---------------------------------------------------------
        q2_sql = f"""
        SELECT
            avg(EXTRACT(EPOCH FROM (resolved_at - detected_at)) / 60.0)::numeric(10, 2) AS mean_mttr,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (resolved_at - detected_at)) / 60.0) AS p95_mttr
        FROM incidents
        WHERE service_id = '{svc_id}'
          AND resolved_at IS NOT NULL;
        """
        # BEFORE (Sequential scan on incidents)
        await session.execute(text("SET enable_bitmapscan = off;"))
        await session.execute(text("SET enable_indexscan = off;"))
        res2_before = (
            (await session.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {q2_sql}"))).scalars().all()
        )
        # AFTER (Index scan on incidents using service_id index)
        await session.execute(text("SET enable_bitmapscan = on;"))
        await session.execute(text("SET enable_indexscan = on;"))
        res2_after = (
            (await session.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {q2_sql}"))).scalars().all()
        )

        results["q2_before"] = "\n".join(res2_before)
        results["q2_after"] = "\n".join(res2_after)

        # ---------------------------------------------------------
        # Query 3: Partial Index on Open Incidents per Service
        # ---------------------------------------------------------
        q3_sql = f"""
        SELECT id, title, status, severity, created_at
        FROM incidents
        WHERE service_id = '{svc_id}'
          AND status IN ('DETECTED', 'TRIGGERED', 'ACKNOWLEDGED', 'INVESTIGATING', 'MITIGATING');
        """
        # BEFORE (Sequential scan on incidents table)
        await session.execute(text("SET enable_bitmapscan = off;"))
        await session.execute(text("SET enable_indexscan = off;"))
        res3_before = (
            (await session.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {q3_sql}"))).scalars().all()
        )
        # AFTER (Partial Index ix_incidents_open_per_service)
        await session.execute(text("SET enable_bitmapscan = on;"))
        await session.execute(text("SET enable_indexscan = on;"))
        res3_after = (
            (await session.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {q3_sql}"))).scalars().all()
        )

        results["q3_before"] = "\n".join(res3_before)
        results["q3_after"] = "\n".join(res3_after)

        return results


if __name__ == "__main__":
    out = asyncio.run(run_benchmarks())
    for k, v in out.items():
        print(f"=== {k.upper()} ===")
        print(v)
        print()

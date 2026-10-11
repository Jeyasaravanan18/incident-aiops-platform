"""schema hardening: check constraints, GIN indexes, partial index, server-side alert fingerprint

Revision ID: 0002_schema_hardening
Revises: 0001_initial_schema
Create Date: 2026-10-11
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_schema_hardening"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Alerts schema hardening: first_seen_at and last_seen_at timestamps
    op.add_column(
        "alerts",
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "alerts",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill first_seen_at and last_seen_at from first_seen and last_seen
    op.execute("UPDATE alerts SET first_seen_at = first_seen, last_seen_at = last_seen")

    # 2. CHECK constraints
    op.create_check_constraint(
        "ck_incidents_ack_after_created",
        "incidents",
        "acknowledged_at IS NULL OR acknowledged_at >= created_at",
    )
    op.create_check_constraint(
        "ck_incidents_res_after_created",
        "incidents",
        "resolved_at IS NULL OR resolved_at >= created_at",
    )
    op.create_check_constraint(
        "ck_alerts_occurrence_count_positive",
        "alerts",
        "occurrence_count >= 1",
    )
    op.create_check_constraint(
        "ck_alerts_last_seen_after_first",
        "alerts",
        "last_seen >= first_seen",
    )
    op.create_check_constraint(
        "ck_service_health_status_code",
        "service_health_checks",
        "http_status IS NULL OR (http_status >= 100 AND http_status <= 599)",
    )
    op.create_check_constraint(
        "ck_service_health_latency_nonneg",
        "service_health_checks",
        "response_time_ms IS NULL OR response_time_ms >= 0",
    )

    # 3. Partial index for open incidents per service
    # Open statuses: DETECTED, TRIGGERED, ACKNOWLEDGED, INVESTIGATING, MITIGATING
    op.create_index(
        "ix_incidents_open_per_service",
        "incidents",
        ["service_id"],
        postgresql_where=sa.text(
            "status IN ('DETECTED', 'TRIGGERED', 'ACKNOWLEDGED', 'INVESTIGATING', 'MITIGATING')"
        ),
    )

    # 4. Real GIN indexes for JSONB containment queries
    op.create_index(
        "ix_alerts_metadata_json_gin",
        "alerts",
        ["metadata_json"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_log_entries_metadata_json_gin",
        "log_entries",
        ["metadata_json"],
        postgresql_using="gin",
    )

    # 5. Generated tsvector column + GIN index on log_entries.message
    op.execute(
        "ALTER TABLE log_entries ADD COLUMN search_vector tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', coalesce(message, ''))) STORED"
    )
    op.create_index(
        "ix_log_entries_search_vector_gin",
        "log_entries",
        ["search_vector"],
        postgresql_using="gin",
    )

    # 6. Generated tsvector column + GIN index on runbooks (title and body)
    op.execute(
        "ALTER TABLE runbooks ADD COLUMN search_vector tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(body, ''))) STORED"
    )
    op.create_index(
        "ix_runbooks_search_vector_gin",
        "runbooks",
        ["search_vector"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_runbooks_search_vector_gin", table_name="runbooks")
    op.execute("ALTER TABLE runbooks DROP COLUMN search_vector")

    op.drop_index("ix_log_entries_search_vector_gin", table_name="log_entries")
    op.execute("ALTER TABLE log_entries DROP COLUMN search_vector")

    op.drop_index("ix_log_entries_metadata_json_gin", table_name="log_entries")
    op.drop_index("ix_alerts_metadata_json_gin", table_name="alerts")
    op.drop_index("ix_incidents_open_per_service", table_name="incidents")

    op.drop_constraint("ck_service_health_latency_nonneg", "service_health_checks", type_="check")
    op.drop_constraint("ck_service_health_status_code", "service_health_checks", type_="check")
    op.drop_constraint("ck_alerts_last_seen_after_first", "alerts", type_="check")
    op.drop_constraint("ck_alerts_occurrence_count_positive", "alerts", type_="check")
    op.drop_constraint("ck_incidents_res_after_created", "incidents", type_="check")
    op.drop_constraint("ck_incidents_ack_after_created", "incidents", type_="check")

    op.drop_column("alerts", "last_seen_at")
    op.drop_column("alerts", "first_seen_at")

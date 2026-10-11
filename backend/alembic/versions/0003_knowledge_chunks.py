"""create knowledge_chunks table with tsvector GIN index and optional pgvector HNSW index, add rag tracking columns to ai_analyses

Revision ID: 0003_knowledge_chunks
Revises: 0002_schema_hardening
Create Date: 2026-10-11
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import UserDefinedType

from alembic import op

revision = "0003_knowledge_chunks"
down_revision = "0002_schema_hardening"
branch_labels = None
depends_on = None


class PGVector(UserDefinedType):
    """Custom SQLAlchemy type representing PostgreSQL vector(N)."""

    def __init__(self, dim: int = 768) -> None:
        self.dim = dim

    def get_col_spec(self, **kw: object) -> str:
        return f"vector({self.dim})"


def upgrade() -> None:
    bind = op.get_bind()

    # Detect if pgvector extension is available in the database engine
    has_vector = bool(
        bind.execute(
            sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
        ).scalar()
    )
    if has_vector:
        bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector;"))

    embedding_type = PGVector(768) if has_vector else postgresql.JSONB()

    # 1. Create knowledge_chunks table
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "service_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("services.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "embedding",
            embedding_type,
            server_default=None if has_vector else "[]",
            nullable=False,
        ),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', content)", persisted=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # 2. Create indexes
    op.create_index(
        "ix_knowledge_chunks_source",
        "knowledge_chunks",
        ["source_type", "source_id"],
    )
    op.create_index(
        "ix_knowledge_chunks_service_id",
        "knowledge_chunks",
        ["service_id"],
    )
    op.create_index(
        "ix_knowledge_chunks_search_vector_gin",
        "knowledge_chunks",
        ["search_vector"],
        postgresql_using="gin",
    )

    if has_vector:
        op.create_index(
            "ix_knowledge_chunks_embedding_hnsw",
            "knowledge_chunks",
            ["embedding"],
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        )

    # 3. Add RAG tracking fields to ai_analyses
    op.add_column("ai_analyses", sa.Column("model_name", sa.String(100), nullable=True))
    op.add_column("ai_analyses", sa.Column("prompt_version", sa.String(50), nullable=True))
    op.add_column(
        "ai_analyses",
        sa.Column(
            "retrieved_chunk_ids",
            postgresql.JSONB(),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "ai_analyses",
        sa.Column(
            "chunk_scores",
            postgresql.JSONB(),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column("ai_analyses", sa.Column("latency_ms", sa.Integer(), nullable=True))
    op.add_column(
        "ai_analyses",
        sa.Column("attempts", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "ai_analyses",
        sa.Column(
            "validity_flags",
            postgresql.JSONB(),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column(
        "ai_analyses",
        sa.Column(
            "fallback_used",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("ai_analyses", "fallback_used")
    op.drop_column("ai_analyses", "validity_flags")
    op.drop_column("ai_analyses", "attempts")
    op.drop_column("ai_analyses", "latency_ms")
    op.drop_column("ai_analyses", "chunk_scores")
    op.drop_column("ai_analyses", "retrieved_chunk_ids")
    op.drop_column("ai_analyses", "prompt_version")
    op.drop_column("ai_analyses", "model_name")

    op.drop_table("knowledge_chunks")

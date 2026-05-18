"""
PULSE DevOps Agent — Database Setup
Uses SQLite via SQLAlchemy async engine.

WHY SQLite?
  - Zero setup — no Postgres/MySQL needed locally
  - File-based: pulse_agent.db is auto-created
  - Async-compatible via aiosqlite
  - Easy to inspect with DB Browser for SQLite

Tables:
  - scan_runs:    Every time user triggers a scan
  - scan_issues:  Individual issues found per run
  - fix_records:  Applied fixes with before/after diff
  - patterns:     Learned bug-fix patterns (Phase 4 seed data)
"""

from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean,
    Text, DateTime, ForeignKey, JSON
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

from core.config import settings


# ── Engine & Session Factory ───────────────────────────────────────────────────

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,        # Print SQL queries in debug mode
    future=True,
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,     # Don't expire objects after commit (important for async)
)


# ── Base Model ─────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── Tables ─────────────────────────────────────────────────────────────────────

class ScanRun(Base):
    """
    Represents one full scan-and-heal run.
    Created when user submits a repository URL.
    """
    __tablename__ = "scan_runs"

    id = Column(String(36), primary_key=True)           # UUID
    repository_url = Column(String(512), nullable=False)
    repository_name = Column(String(255))
    branch_name = Column(String(255))
    author_name = Column(String(255))                    # Who triggered the run

    # Status lifecycle: pending → running → completed/failed
    status = Column(String(50), default="pending")
    current_stage = Column(String(100), default="initializing")
    progress = Column(Integer, default=0)               # 0-100

    # Timing
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    duration_seconds = Column(Float)

    # Results summary
    total_issues_found = Column(Integer, default=0)
    total_fixes_applied = Column(Integer, default=0)
    total_fixes_failed = Column(Integer, default=0)

    # Scoring (your unique features)
    health_score = Column(Float)                        # 0-100 repo health
    severity_score = Column(Float)                      # Weighted severity
    ai_confidence_score = Column(Float)                 # AI fix confidence

    # CI/CD
    cicd_status = Column(String(50))
    cicd_iterations = Column(Integer, default=0)
    pull_request_url = Column(String(512))
    commit_sha = Column(String(40))

    # Error info
    error_message = Column(Text)

    # Relationships
    issues = relationship("ScanIssue", back_populates="run", cascade="all, delete-orphan")
    fixes = relationship("FixRecord", back_populates="run", cascade="all, delete-orphan")


class ScanIssue(Base):
    """
    Individual code issue found during scanning.
    Each run can have many issues across many files.
    """
    __tablename__ = "scan_issues"

    id = Column(String(36), primary_key=True)
    run_id = Column(String(36), ForeignKey("scan_runs.id"), nullable=False)

    file_path = Column(String(512), nullable=False)
    line_number = Column(Integer, default=0)
    column_number = Column(Integer, default=0)

    # Issue classification
    bug_type = Column(String(50))       # LINTING, SYNTAX, TYPE_ERROR, IMPORT, LOGIC, SECURITY
    severity = Column(String(20))       # critical, high, medium, low, info
    severity_score = Column(Float)      # Numeric score 0-10
    source = Column(String(50))         # pylint, flake8, mypy, bandit, ai-analysis

    message = Column(Text)
    symbol = Column(String(100))        # Error code like E501, W0611

    # Whether a fix was applied
    fixed = Column(Boolean, default=False)
    fix_id = Column(String(36))         # Reference to FixRecord

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    run = relationship("ScanRun", back_populates="issues")


class FixRecord(Base):
    """
    A fix that was generated and applied.
    Stores before/after code for diff view and rollback.
    """
    __tablename__ = "fix_records"

    id = Column(String(36), primary_key=True)
    run_id = Column(String(36), ForeignKey("scan_runs.id"), nullable=False)

    file_path = Column(String(512), nullable=False)
    bug_type = Column(String(50))
    description = Column(Text)

    # Diff data
    before_code = Column(Text)
    after_code = Column(Text)
    line_number = Column(Integer)

    # Fix metadata
    fix_strategy = Column(String(50))   # ai, rule-based, offline
    ai_confidence = Column(Float)       # 0.0-1.0 confidence score
    commit_message = Column(String(512))
    commit_sha = Column(String(40))

    # Status
    status = Column(String(50), default="pending")  # pending, applied, failed, rolled_back
    error_message = Column(Text)

    applied_at = Column(DateTime)
    rolled_back_at = Column(DateTime)   # Rollback support!

    # Relationship
    run = relationship("ScanRun", back_populates="fixes")


# ── Database Lifecycle ─────────────────────────────────────────────────────────

async def init_db():
    """
    Create all tables on startup.
    Safe to call multiple times — only creates tables that don't exist.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """
    FastAPI dependency: yields a DB session per request, auto-closes after.

    Usage in route:
        async def my_route(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

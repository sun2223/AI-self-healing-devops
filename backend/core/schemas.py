"""
PULSE DevOps Agent — Pydantic Request/Response Schemas

WHY separate schemas from DB models?
  - DB models (database.py) define HOW data is stored
  - Schemas define HOW data enters/leaves the API
  - Keeps validation logic separate from persistence logic
  - Allows API to evolve without breaking DB schema
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, HttpUrl, Field, field_validator


# ── Request Schemas (what client sends) ───────────────────────────────────────

class StartScanRequest(BaseModel):
    """
    Request to start a new repository scan.
    Sent as POST /api/v1/scans
    """
    repository_url: str = Field(
        ...,
        description="GitHub repository URL",
        examples=["https://github.com/username/my-repo"]
    )
    author_name: str = Field(
        default="anonymous",
        description="Name of person triggering the scan",
        max_length=100
    )
    branch_name: Optional[str] = Field(
        default=None,
        description="Branch to create for fixes (auto-generated if not provided)"
    )
    github_token: Optional[str] = Field(
        default=None,
        description="GitHub OAuth token (optional — uses server token if not provided)"
    )
    # Feature flags
    enable_ai_fixes: bool = Field(
        default=True,
        description="Use AI to generate fixes (requires API key)"
    )
    offline_mode: bool = Field(
        default=False,
        description="Use rule-based fixes only — no API calls"
    )
    max_files: Optional[int] = Field(
        default=50,
        ge=1, le=200,
        description="Maximum number of files to scan"
    )

    @field_validator("repository_url")
    @classmethod
    def validate_repo_url(cls, v: str) -> str:
        """Ensure URL is a GitHub URL"""
        if not v.startswith("https://github.com/"):
            raise ValueError("Only GitHub repository URLs are supported (https://github.com/...)")
        return v.rstrip("/")


class FixIssueRequest(BaseModel):
    """
    Request to heal/fix a specific issue.
    """
    issue_id: str = Field(..., description="ID of the issue to fix")
    



# ── Response Schemas (what server sends back) ──────────────────────────────────

class ScanStartedResponse(BaseModel):
    """Response when a scan is successfully started"""
    scan_id: str
    status: str = "pending"
    message: str
    repository_url: str
    branch_name: str
    estimated_duration_seconds: int = 120


class IssueResponse(BaseModel):
    """A single detected issue"""
    id: str
    file_path: str
    line_number: int
    column_number: int = 0
    bug_type: str
    severity: str          # critical, high, medium, low, info
    severity_score: float  # 0.0-10.0 (your unique feature)
    message: str
    symbol: str = ""
    source: str            # pylint, flake8, mypy, bandit, ai-analysis
    fixed: bool = False


class FixResponse(BaseModel):
    """A fix that was applied"""
    id: str
    file_path: str
    bug_type: str
    description: str
    before_code: str
    after_code: str
    line_number: int
    fix_strategy: str      # ai, rule-based, offline
    ai_confidence: float   # 0.0-1.0 (your unique feature)
    status: str            # applied, failed, rolled_back
    commit_sha: Optional[str] = None


class HealthScoreResponse(BaseModel):
    """Repository health score breakdown (your unique feature)"""
    score: float           # 0-100
    grade: str             # A, B, C, D, F
    label: str             # "Excellent", "Needs Attention", etc.
    total_issues: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    info_count: int
    top_problem_files: List[str]


class ScanStatusResponse(BaseModel):
    """Real-time status of a running scan"""
    scan_id: str
    status: str
    current_stage: str
    progress: int          # 0-100
    repository_url: str
    repository_name: Optional[str] = None
    author_name: Optional[str] = None

    # Timing
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None

    # Results (populated as scan progresses)
    total_issues_found: int = 0
    total_fixes_applied: int = 0
    total_fixes_failed: int = 0

    # Scoring
    health_score: Optional[HealthScoreResponse] = None
    ai_confidence_score: Optional[float] = None  # Average confidence across all fixes

    # CI/CD
    cicd_status: Optional[str] = None
    cicd_iterations: int = 0
    pull_request_url: Optional[str] = None
    commit_sha: Optional[str] = None

    # Error
    error_message: Optional[str] = None


class ScanResultsResponse(BaseModel):
    """Complete results of a finished scan"""
    scan_id: str
    status: str
    repository_url: str
    repository_name: Optional[str] = None

    # Health scoring (your unique features)
    health_score: Optional[HealthScoreResponse] = None
    ai_confidence_score: Optional[float] = None

    # Issues and fixes
    issues: List[IssueResponse] = []
    fixes: List[FixResponse] = []

    # File tree for visualization
    file_tree: Optional[Dict[str, Any]] = None

    # Bug heatmap (your unique feature)
    bug_heatmap: Optional[Dict[str, Any]] = None

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None

    # Git info
    pull_request_url: Optional[str] = None
    commit_sha: Optional[str] = None
    branch_name: Optional[str] = None


class ScanListResponse(BaseModel):
    """Paginated list of scans"""
    total: int
    page: int
    page_size: int
    scans: List[ScanStatusResponse]


class SystemHealthResponse(BaseModel):
    """System health check — tells frontend which features are available"""
    status: str = "healthy"
    version: str
    timestamp: datetime
    features: Dict[str, Any]   # Which capabilities are enabled
    tools_available: Dict[str, bool]  # Which analysis tools are installed


class ErrorResponse(BaseModel):
    """Standard error response"""
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None

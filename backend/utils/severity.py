"""
PULSE DevOps Agent — Severity Scoring System

YOUR UNIQUE FEATURE — Not in the original RIFT project.

How it works:
  Every issue found gets a severity score from 0.0 to 10.0
  The repository health score (0-100) is derived from all issue scores combined.

Severity levels:
  critical (8-10): Syntax errors, security vulnerabilities — code won't run
  high     (6-8):  Logic errors, import failures — code runs but breaks
  medium   (4-6):  Type errors, undefined names — code may work but is unsafe
  low      (2-4):  Linting, style issues — code works fine
  info     (0-2):  Suggestions, best practices — optional fixes

Health Score formula:
  Start at 100.
  Deduct weighted points per issue severity.
  Score = max(0, 100 - sum(deductions))

Why this matters:
  Instead of just showing "35 issues", PULSE shows:
    Repository Health: 62/100 ⚠️ Needs Attention
    Critical Issues:  3 (blocking)
    High Issues:      7
    AI Confidence:    87%
"""

from dataclasses import dataclass
from typing import List, Optional


# ── Severity Classification Rules ──────────────────────────────────────────────

# Maps (bug_type, source) → base severity score
SEVERITY_RULES = {
    # Bug type rules
    "SYNTAX":     9.0,   # Code won't run at all
    "SECURITY":   8.5,   # Security vulnerability
    "LOGIC":      7.0,   # Code runs but produces wrong results
    "IMPORT":     6.5,   # Import failures break modules
    "TYPE_ERROR": 5.0,   # Type mismatch — may fail at runtime
    "LINTING":    2.5,   # Style issues — code works fine
    "INDENTATION":4.0,   # Can break Python code
}

# Source modifier — some tools are more accurate than others
SOURCE_MODIFIERS = {
    "ast-parser":   1.2,   # Direct Python AST — most accurate
    "bandit":       1.15,  # Security-focused — high confidence
    "mypy":         1.1,   # Type checker — reliable
    "pylint":       1.0,   # Good linter — baseline
    "flake8":       0.9,   # Style checker — slightly less severe
    "ai-analysis":  0.85,  # AI can have false positives
}

# Per-issue health score deduction
SEVERITY_DEDUCTIONS = {
    "critical": 8.0,
    "high":     4.0,
    "medium":   2.0,
    "low":      0.5,
    "info":     0.1,
}


# ── Data Classes ───────────────────────────────────────────────────────────────

@dataclass
class IssueSeverity:
    """Severity assessment for a single issue"""
    level: str           # critical, high, medium, low, info
    score: float         # 0.0 - 10.0
    deduction: float     # Health score deduction for this issue
    reasoning: str       # Why this severity was assigned


@dataclass
class RepositoryHealthScore:
    """Overall repository health assessment"""
    score: float                  # 0-100 (100 = perfect)
    grade: str                    # A, B, C, D, F
    label: str                    # "Healthy", "Needs Attention", "Critical"
    total_issues: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    info_count: int
    top_problem_files: List[str]  # Files with most issues


# ── Scoring Functions ──────────────────────────────────────────────────────────

def score_issue(
    bug_type: str,
    source: str,
    message: str = "",
    severity_hint: Optional[str] = None,
) -> IssueSeverity:
    """
    Calculate severity score for a single issue.

    Args:
        bug_type:      Issue category (SYNTAX, LINTING, etc.)
        source:        Tool that found it (pylint, flake8, etc.)
        message:       Issue message text (for keyword boosting)
        severity_hint: Optional hint from tool ('error', 'warning', 'info')

    Returns:
        IssueSeverity with score, level and reasoning

    Example:
        severity = score_issue("SYNTAX", "ast-parser", "Missing colon")
        # severity.level = "critical"
        # severity.score = 10.0
    """
    # Base score from bug type
    base_score = SEVERITY_RULES.get(bug_type.upper(), 3.0)

    # Apply source modifier
    modifier = SOURCE_MODIFIERS.get(source.lower(), 1.0)
    score = min(10.0, base_score * modifier)

    # Boost for specific dangerous keywords in message
    message_lower = message.lower()
    keyword_boosts = {
        "sql injection": 2.0,
        "hardcoded password": 2.0,
        "eval(": 1.5,
        "exec(": 1.5,
        "os.system": 1.0,
        "pickle": 1.0,
        "undefined": 0.5,
        "recursion": 0.5,
    }
    for keyword, boost in keyword_boosts.items():
        if keyword in message_lower:
            score = min(10.0, score + boost)
            break

    # If tool provided a severity hint, use it to adjust
    if severity_hint == "error":
        score = max(score, 6.0)  # At least "high" if tool says error
    elif severity_hint == "info":
        score = min(score, 3.0)  # Cap at "low" if tool says info

    # Map score to level
    level = _score_to_level(score)
    deduction = SEVERITY_DEDUCTIONS[level]
    reasoning = f"{bug_type} from {source} → base {base_score:.1f} × {modifier:.2f} = {score:.1f}"

    return IssueSeverity(
        level=level,
        score=round(score, 2),
        deduction=deduction,
        reasoning=reasoning,
    )


def calculate_health_score(issues: List[dict]) -> RepositoryHealthScore:
    """
    Calculate the repository health score from all detected issues.

    Args:
        issues: List of issue dicts with 'bug_type', 'source', 'severity', 'file_path'

    Returns:
        RepositoryHealthScore with full breakdown

    Example:
        health = calculate_health_score(all_issues)
        print(f"Health: {health.score}/100 ({health.grade})")
    """
    if not issues:
        return RepositoryHealthScore(
            score=100.0,
            grade="A",
            label="Excellent — No Issues Found",
            total_issues=0,
            critical_count=0,
            high_count=0,
            medium_count=0,
            low_count=0,
            info_count=0,
            top_problem_files=[],
        )

    # Count by severity level
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    total_deduction = 0.0
    file_issue_counts: dict = {}

    for issue in issues:
        severity = score_issue(
            bug_type=issue.get("bug_type", "LINTING"),
            source=issue.get("source", "pylint"),
            message=issue.get("message", ""),
            severity_hint=issue.get("severity"),
        )
        counts[severity.level] += 1
        total_deduction += severity.deduction

        # Track per-file issue counts
        file_path = issue.get("file_path", "unknown")
        file_issue_counts[file_path] = file_issue_counts.get(file_path, 0) + 1

    # Calculate health score (never below 0)
    health = max(0.0, 100.0 - total_deduction)
    health = round(health, 1)

    # Grade and label
    grade, label = _health_to_grade(health)

    # Top problem files (sorted by issue count)
    top_files = sorted(file_issue_counts, key=file_issue_counts.get, reverse=True)[:5]

    return RepositoryHealthScore(
        score=health,
        grade=grade,
        label=label,
        total_issues=len(issues),
        critical_count=counts["critical"],
        high_count=counts["high"],
        medium_count=counts["medium"],
        low_count=counts["low"],
        info_count=counts["info"],
        top_problem_files=top_files,
    )


def _score_to_level(score: float) -> str:
    """Convert numeric score (0-10) to severity level string"""
    if score >= 8.0:
        return "critical"
    elif score >= 6.0:
        return "high"
    elif score >= 4.0:
        return "medium"
    elif score >= 2.0:
        return "low"
    else:
        return "info"


def _health_to_grade(health: float) -> tuple:
    """Convert health score (0-100) to grade letter and label"""
    if health >= 90:
        return "A", "Excellent"
    elif health >= 75:
        return "B", "Good"
    elif health >= 60:
        return "C", "Needs Attention"
    elif health >= 40:
        return "D", "Poor"
    else:
        return "F", "Critical — Immediate Action Required"

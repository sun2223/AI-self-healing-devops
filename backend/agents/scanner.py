"""
PULSE DevOps Agent — Scanner Agent

This agent is responsible for:
  1. Cloning a repository (cross-platform, utilizing GITHUB_TOKEN if private)
  2. Discovering files (supporting multiple languages, focus on Python/JS/Go)
  3. Running static analysis tools (pylint, flake8, mypy, bandit)
  4. Parsing their outputs into a standardized format
  5. Applying severity scoring and calculating repository health
"""

import json
import os
import re
import sys
import shutil
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

from core.config import settings
from utils.logger import get_logger
from utils.platform_utils import run_command, normalize_path, get_relative_path
from utils.severity import score_issue, calculate_health_score

logger = get_logger(__name__)


class ScannerAgent:
    """
    Scanner Agent — analyzes a repository's source code using static analysis tools.
    """

    def __init__(self, scan_id: str, repo_url: str, branch_name: Optional[str] = None):
        self.scan_id = scan_id
        self.repo_url = repo_url
        self.branch_name = branch_name or "main"
        
        # Base folder for all clones
        self.base_clone_dir = Path("cloned_repos")
        self.repo_dir = self.base_clone_dir / scan_id
        
        # Resolve static analysis tools paths from venv if present (Windows robust check)
        self.tool_paths = self._resolve_tool_paths()

    def _resolve_tool_paths(self) -> Dict[str, str]:
        """Resolve executable paths for analysis tools. Uses venv path if available."""
        tools = ["git", "pylint", "flake8", "mypy", "bandit"]
        resolved = {}
        
        # Try local venv path first (sys.executable's folder)
        venv_bin = Path(sys.executable).parent
        
        for tool in tools:
            # Check venv first (adds .exe on Windows)
            win_exe = venv_bin / f"{tool}.exe"
            unix_exe = venv_bin / tool
            
            if win_exe.exists():
                resolved[tool] = str(win_exe)
            elif unix_exe.exists():
                resolved[tool] = str(unix_exe)
            else:
                # Fallback to system PATH via shutil.which
                fallback = shutil.which(tool)
                if fallback:
                    resolved[tool] = fallback
                else:
                    resolved[tool] = tool  # Just use plain command and hope it's on path
                    
        return resolved

    async def execute_scan(self, on_progress=None) -> Dict[str, Any]:
        """
        Runs the full clone & scan workflow.
        
        Args:
            on_progress: Async callback function that receives progress updates: (stage: str, progress: int, message: str)
            
        Returns:
            Dict containing scan results (issues, health score, etc.)
        """
        results = {
            "status": "success",
            "issues": [],
            "health_score": 100.0,
            "metrics": {},
            "error": None
        }

        try:
            # 1. Clone repository
            if on_progress:
                await on_progress("cloning", 10, "Cloning repository...")
            
            success, err_msg = await self.clone_repository()
            if not success:
                results["status"] = "failed"
                results["error"] = f"Clone failed: {err_msg}"
                return results

            # 2. Locate files to scan
            if on_progress:
                await on_progress("scanning", 30, "Analyzing project structure...")
            
            python_files = self.find_files(".py")
            js_files = self.find_files(".js")
            go_files = self.find_files(".go")
            
            total_files = len(python_files) + len(js_files) + len(go_files)
            logger.info("Found files to scan", python=len(python_files), js=len(js_files), go=len(go_files))

            if total_files == 0:
                if on_progress:
                    await on_progress("completed", 100, "Scan completed (no supported files found).")
                return results

            all_issues = []

            # 3. Run Python static analysis if Python files exist
            if python_files:
                # Pylint
                if on_progress:
                    await on_progress("scanning", 45, "Running pylint code analysis...")
                pylint_issues = await self.run_pylint()
                all_issues.extend(pylint_issues)
                
                # Flake8
                if on_progress:
                    await on_progress("scanning", 60, "Running flake8 style analysis...")
                flake8_issues = await self.run_flake8()
                all_issues.extend(flake8_issues)
                
                # Bandit
                if on_progress:
                    await on_progress("scanning", 75, "Running bandit security scans...")
                bandit_issues = await self.run_bandit()
                all_issues.extend(bandit_issues)

                # Mypy
                if on_progress:
                    await on_progress("scanning", 85, "Running mypy type verification...")
                mypy_issues = await self.run_mypy()
                all_issues.extend(mypy_issues)

            # 4. Standardize issues & Calculate Severity and Health Scorer
            if on_progress:
                await on_progress("scoring", 95, "Calculating repository health score...")

            # Add severity scores and read code snippets
            scored_issues = []
            for issue in all_issues:
                # Add full filepath inside repo_dir to fetch code snippet
                rel_path = issue["file_path"]
                full_path = self.repo_dir / rel_path
                
                snippet = ""
                if full_path.exists() and full_path.is_file():
                    try:
                        lines = full_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                        line_idx = issue["line"] - 1
                        if 0 <= line_idx < len(lines):
                            snippet = lines[line_idx].strip()
                    except Exception as e:
                        logger.warning("Failed to read snippet", file=rel_path, error=str(e))
                
                # Compute severity level and score
                severity_info = score_issue(
                    bug_type=issue["bug_type"],
                    source=issue["source"],
                    message=issue["message"],
                    severity_hint=issue.get("severity_hint")
                )
                
                scored_issues.append({
                    "file_path": rel_path,
                    "line": issue["line"],
                    "column": issue["column"],
                    "bug_type": issue["bug_type"],
                    "source": issue["source"],
                    "severity": severity_info.level,
                    "severity_score": severity_info.score,
                    "message": issue["message"],
                    "code_snippet": snippet,
                    "reasoning": severity_info.reasoning
                })

            # Sort issues by severity score descending
            scored_issues.sort(key=lambda x: x["severity_score"], reverse=True)

            # Compute health score
            health_report = calculate_health_score(scored_issues)

            results["issues"] = scored_issues
            results["health_score"] = health_report.score
            results["metrics"] = {
                "grade": health_report.grade,
                "label": health_report.label,
                "total_issues": health_report.total_issues,
                "critical_count": health_report.critical_count,
                "high_count": health_report.high_count,
                "medium_count": health_report.medium_count,
                "low_count": health_report.low_count,
                "info_count": health_report.info_count,
                "top_problem_files": health_report.top_problem_files
            }

            if on_progress:
                await on_progress("completed", 100, f"Scan complete! Repository Health: {health_report.score}/100")

        except Exception as e:
            logger.exception("Scan workflow failed")
            results["status"] = "failed"
            results["error"] = str(e)
            if on_progress:
                await on_progress("failed", 100, f"Scan failed: {str(e)}")

        finally:
            # Cleanup cloned repository directory to save space (Optional, but let's keep it for Healer Agent Phase 3)
            pass

        return results

    async def clone_repository(self) -> Tuple[bool, str]:
        """Clones the repository locally using Git with branch-level and token-level resilience."""
        # Create cloned_repos dir if not exists
        self.base_clone_dir.mkdir(exist_ok=True)
        
        # Clean up any existing directory for this scan_id
        if self.repo_dir.exists():
            shutil.rmtree(self.repo_dir, ignore_errors=True)

        # Build authenticated URL if token is present
        repo_url = self.repo_url
        if settings.GITHUB_TOKEN:
            token_prefix = f"https://{settings.GITHUB_TOKEN}@"
            repo_url = self.repo_url.replace("https://", token_prefix)

        logger.info("Cloning repository", url=self.repo_url, target=str(self.repo_dir))
        
        # First, try to clone the specified branch if it doesn't look like an auto-generated fix branch
        is_auto_fix_branch = self.branch_name.startswith("pulse-fix-")
        
        if not is_auto_fix_branch:
            # 1a. Try to clone specified branch with token if present
            args = [
                self.tool_paths["git"],
                "clone",
                "--branch", self.branch_name,
                "--depth", "1",  # Shallow clone to speed up download and save disk space
                repo_url,
                str(self.repo_dir)
            ]
            result = await run_command(args, timeout=120)
            if result.success:
                logger.info("Repository cloned successfully on specified branch with token", scan_id=self.scan_id, branch=self.branch_name)
                return True, ""
            
            # 1b. If token clone failed, try cloning without the token (in case token is restricted but repo is public)
            if settings.GITHUB_TOKEN:
                logger.warning("Token clone failed on specified branch, retrying without token", branch=self.branch_name)
                if self.repo_dir.exists():
                    shutil.rmtree(self.repo_dir, ignore_errors=True)
                args = [
                    self.tool_paths["git"],
                    "clone",
                    "--branch", self.branch_name,
                    "--depth", "1",
                    self.repo_url,  # Plain public URL
                    str(self.repo_dir)
                ]
                result = await run_command(args, timeout=120)
                if result.success:
                    logger.info("Repository cloned successfully on specified branch without token", scan_id=self.scan_id, branch=self.branch_name)
                    return True, ""
            
            logger.warning("Git clone on specified branch failed, trying default branch fallback", branch=self.branch_name, stderr=result.stderr)
        
        # 2. Fallback/Default: Clone default branch (no --branch flag)
        # 2a. Try to clone default branch with token if present
        if self.repo_dir.exists():
            shutil.rmtree(self.repo_dir, ignore_errors=True)
            
        args = [
            self.tool_paths["git"],
            "clone",
            "--depth", "1",
            repo_url,
            str(self.repo_dir)
        ]
        result = await run_command(args, timeout=120)
        if result.success:
            logger.info("Repository cloned successfully on default branch with token", scan_id=self.scan_id)
            return True, ""
            
        # 2b. If default branch clone with token failed, try without token (handles restricted token + public repo)
        if settings.GITHUB_TOKEN:
            logger.warning("Token clone failed on default branch, retrying default branch clone without token")
            if self.repo_dir.exists():
                shutil.rmtree(self.repo_dir, ignore_errors=True)
            args = [
                self.tool_paths["git"],
                "clone",
                "--depth", "1",
                self.repo_url,  # Plain public URL
                str(self.repo_dir)
            ]
            result = await run_command(args, timeout=120)
            if result.success:
                logger.info("Repository cloned successfully on default branch without token", scan_id=self.scan_id)
                return True, ""
                
        logger.error("Git clone failed on all default branch fallback configurations", stderr=result.stderr)
        return False, result.stderr or "Unknown git error"

    def find_files(self, extension: str) -> List[str]:
        """Finds all files in the cloned repository with the specified extension."""
        if not self.repo_dir.exists():
            return []
        
        matched_files = []
        for path in self.repo_dir.rglob(f"*{extension}"):
            # Skip hidden folders (.git, .github, venv, node_modules)
            parts = path.relative_to(self.repo_dir).parts
            if any(p.startswith(".") or p in ["venv", "node_modules", "env", "dist"] for p in parts):
                continue
                
            if path.is_file():
                matched_files.append(str(path))
                
        return matched_files

    async def run_pylint(self) -> List[dict]:
        """Runs Pylint on the cloned repository and parses results."""
        logger.info("Running pylint scan")
        
        args = [
            self.tool_paths["pylint"],
            "--output-format=json",
            "--recursive=y",
            "."
        ]
        
        result = await run_command(args, cwd=str(self.repo_dir), timeout=90)
        issues = []
        
        # Pylint exits with non-zero on issues found, so we check if stdout has content
        if not result.stdout.strip():
            return issues
            
        try:
            raw_issues = json.loads(result.stdout)
            for raw in raw_issues:
                # Map pylint category to PULSE bug_type
                pylint_type = raw.get("type", "convention")
                bug_type = "LINTING"
                if pylint_type == "fatal" or pylint_type == "error":
                    bug_type = "SYNTAX"
                elif pylint_type == "warning":
                    bug_type = "LOGIC"
                    
                issues.append({
                    "file_path": raw.get("path", ""),
                    "line": raw.get("line", 1),
                    "column": raw.get("column", 0),
                    "bug_type": bug_type,
                    "source": "pylint",
                    "severity_hint": "error" if pylint_type in ["error", "fatal"] else "warning",
                    "message": f"[{raw.get('message-id', '')}] {raw.get('message', '')}"
                })
        except Exception as e:
            logger.warning("Failed to parse pylint JSON", error=str(e), stdout=result.stdout[:200])
            
        return issues

    async def run_flake8(self) -> List[dict]:
        """Runs Flake8 on the cloned repository and parses results."""
        logger.info("Running flake8 scan")
        
        # Format string lets us parse flake8 output easily
        # format: filename:line:col:code:message
        fmt = "%(path)s:%(row)d:%(col)d:%(code)s:%(text)s"
        args = [
            self.tool_paths["flake8"],
            f"--format={fmt}",
            "--exclude=venv,node_modules,.git,__pycache__",
            "."
        ]
        
        result = await run_command(args, cwd=str(self.repo_dir), timeout=90)
        issues = []
        
        if not result.stdout.strip():
            return issues
            
        # Parse output line-by-line
        for line in result.stdout.splitlines():
            parts = line.strip().split(":", 4)
            if len(parts) >= 5:
                file_path, row, col, code, message = parts
                
                # Categorize based on code
                bug_type = "LINTING"
                if code.startswith("E9") or code.startswith("F82"):
                    # Syntax or undefined name errors
                    bug_type = "SYNTAX"
                elif code.startswith("F"):
                    # Pyflakes errors (logic/undefined)
                    bug_type = "LOGIC"
                    
                issues.append({
                    "file_path": file_path,
                    "line": int(row),
                    "column": int(col),
                    "bug_type": bug_type,
                    "source": "flake8",
                    "severity_hint": "error" if bug_type == "SYNTAX" else "warning",
                    "message": f"[{code}] {message}"
                })
                
        return issues

    async def run_bandit(self) -> List[dict]:
        """Runs Bandit security scans and parses results."""
        logger.info("Running bandit security scan")
        
        args = [
            self.tool_paths["bandit"],
            "-f", "json",
            "-r",
            "--exclude", "venv,node_modules,.git",
            "."
        ]
        
        result = await run_command(args, cwd=str(self.repo_dir), timeout=90)
        issues = []
        
        if not result.stdout.strip():
            return issues
            
        try:
            data = json.loads(result.stdout)
            results = data.get("results", [])
            for raw in results:
                # Map bandit severity to PULSE hints
                raw_severity = raw.get("issue_severity", "LOW").lower()
                
                issues.append({
                    "file_path": raw.get("filename", ""),
                    "line": raw.get("line_number", 1),
                    "column": 0,
                    "bug_type": "SECURITY",
                    "source": "bandit",
                    "severity_hint": "error" if raw_severity == "high" else "warning",
                    "message": f"[{raw.get('test_id', '')}] {raw.get('issue_text', '')} (Confidence: {raw.get('issue_confidence', 'MEDIUM')})"
                })
        except Exception as e:
            logger.warning("Failed to parse bandit JSON", error=str(e), stdout=result.stdout[:200])
            
        return issues

    async def run_mypy(self) -> List[dict]:
        """Runs Mypy type checker and parses results."""
        logger.info("Running mypy type check")
        
        args = [
            self.tool_paths["mypy"],
            "--ignore-missing-imports",
            "--shadow-file",  # speeds up runs
            "--exclude", "(venv|node_modules|\\..*)",
            "."
        ]
        
        result = await run_command(args, cwd=str(self.repo_dir), timeout=120)
        issues = []
        
        if not result.stdout.strip():
            return issues
            
        # Standard mypy output is: filename:line: error_level: message
        # e.g., src/main.py:12: error: Name 'x' is not defined
        pattern = re.compile(r"^([^:]+):(\d+):(?:\d+:)?\s*([a-z]+):\s*(.*)$")
        
        for line in result.stdout.splitlines():
            match = pattern.match(line.strip())
            if match:
                file_path, row, level, message = match.groups()
                if level == "note":
                    continue  # Skip informational notes
                    
                issues.append({
                    "file_path": file_path,
                    "line": int(row),
                    "column": 0,
                    "bug_type": "TYPE_ERROR",
                    "source": "mypy",
                    "severity_hint": "error" if level == "error" else "warning",
                    "message": message
                })
                
        return issues

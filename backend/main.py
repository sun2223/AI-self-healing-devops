"""
PULSE DevOps Agent — FastAPI Main Application Entry Point

ARCHITECTURE OVERVIEW:
  This file wires everything together:
    1. FastAPI app with lifespan (startup/shutdown hooks)
    2. Socket.IO server for real-time WebSocket updates
    3. CORS middleware for frontend communication
    4. API routers mounted at /api/v1/
    5. Health check endpoints

FLOW:
  Client → POST /api/v1/scans → background task starts
         → WebSocket /ws connects → receives live updates
         → GET /api/v1/scans/{id} → fetches results

HOW TO RUN:
  cd backend
  uvicorn main:socket_app --host 0.0.0.0 --port 8000 --reload

  Note: We use `main:socket_app` NOT `main:app`
  because Socket.IO wraps the FastAPI app.
"""

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, Optional

import socketio
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config import settings
from core.database import init_db
from core.schemas import SystemHealthResponse, StartScanRequest, ScanStartedResponse, FixIssueRequest
from utils.logger import get_logger, setup_logging
from utils.platform_utils import get_available_tools

setup_logging()

logger = get_logger(__name__)

# ── In-Memory Run Store ────────────────────────────────────────────────────────
# Phase 1: Store active runs in memory (fast, no DB queries needed for status)
# Phase 4+: We'll persist completed runs to SQLite
active_runs: Dict[str, Any] = {}


# ── Socket.IO Server ───────────────────────────────────────────────────────────
# Handles real-time WebSocket communication with the React frontend
# Uses 'asgi' mode so it integrates cleanly with FastAPI
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",   # Allow frontend on any port during development
    logger=False,               # Disable verbose Socket.IO logs
    engineio_logger=False,
)


# ── App Lifespan (startup/shutdown) ───────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs code on startup BEFORE accepting requests,
    and on shutdown AFTER the last request.

    Startup:
      - Initialize SQLite database (creates tables if they don't exist)
      - Log available tools
      - Log configuration summary

    Shutdown:
      - Clean up any running tasks
    """
    # ── STARTUP ──
    logger.info("🚀 PULSE DevOps Agent starting up...", version=settings.APP_VERSION)

    # Create DB tables (safe to call even if tables exist)
    await init_db()
    logger.info("✅ Database initialized", db=settings.DATABASE_URL)

    # Report available analysis tools
    tools = get_available_tools()
    available = [t for t, ok in tools.items() if ok]
    missing = [t for t, ok in tools.items() if not ok]
    logger.info("🔧 Analysis tools available", tools=available)
    if missing:
        logger.warning(
            "⚠️  Some tools not found — install them for full functionality",
            missing=missing,
            hint="pip install pylint flake8 mypy bandit"
        )

    # Report AI mode
    logger.info(f"🤖 AI mode: {settings.active_llm.upper()}", llm=settings.active_llm)
    if not settings.llm_available:
        logger.warning(
            "⚠️  No AI API keys found — running in OFFLINE mode",
            hint="Add OPENAI_API_KEY or GEMINI_API_KEY to your .env file"
        )

    logger.info(
        "✅ PULSE ready",
        url=f"http://localhost:{settings.PORT}",
        docs=f"http://localhost:{settings.PORT}/docs"
    )

    yield  # ← App runs here

    # ── SHUTDOWN ──
    logger.info("👋 PULSE DevOps Agent shutting down...")


# ── FastAPI App ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="PULSE DevOps Agent API",
    description=(
        "Pipeline Understanding, Learning & Self-healing Engine\n\n"
        "An AI-powered DevOps agent that scans repositories, detects bugs, "
        "applies fixes, and monitors CI/CD pipelines.\n\n"
        "**Custom Features:**\n"
        "- Severity Scoring System (0-10 per issue)\n"
        "- Repository Health Score (0-100)\n"
        "- AI Confidence Score per fix\n"
        "- Rollback System\n"
        "- Offline Mode (no API key needed)\n"
        "- Multi-language support"
    ),
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",     # Swagger UI at http://localhost:8000/docs
    redoc_url="/redoc",   # ReDoc at http://localhost:8000/redoc
)

# ── Mount Socket.IO ────────────────────────────────────────────────────────────
# IMPORTANT: socket_app wraps the FastAPI app
# Always run uvicorn with `main:socket_app` not `main:app`
socket_app = socketio.ASGIApp(sio, app)

# ── CORS Middleware ────────────────────────────────────────────────────────────
# Allows the React frontend (localhost:5173) to call our backend (localhost:8000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # In production, restrict to your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Socket.IO Events ───────────────────────────────────────────────────────────

@sio.event
async def connect(sid: str, environ: dict):
    """Called when a frontend client connects via WebSocket"""
    logger.info("Client connected", sid=sid)
    await sio.emit("connected", {"sid": sid, "message": "Connected to PULSE"}, room=sid)


@sio.event
async def disconnect(sid: str):
    """Called when a frontend client disconnects"""
    logger.info("Client disconnected", sid=sid)


@sio.event
async def subscribe_scan(sid: str, data: dict):
    """
    Frontend subscribes to updates for a specific scan.
    After subscribing, the client receives all 'scan_update' events for that scan.

    Frontend usage:
        socket.emit('subscribe_scan', { scan_id: 'abc-123' })
        socket.on('scan_update', (data) => { ... })
    """
    scan_id = data.get("scan_id")
    if scan_id:
        room = f"scan_{scan_id}"
        await sio.enter_room(sid, room)
        logger.info("Client subscribed to scan", sid=sid, scan_id=scan_id)
        await sio.emit("subscribed", {"scan_id": scan_id}, room=sid)

        # If scan is already in progress, send current state immediately
        if scan_id in active_runs:
            current = active_runs[scan_id]
            await sio.emit("scan_update", {
                "scan_id": scan_id,
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "stage": current.get("current_stage", "initializing"),
                    "progress": current.get("progress", 0),
                    "status": current.get("status", "pending"),
                }
            }, room=sid)


async def broadcast_scan_update(scan_id: str, data: dict):
    """
    Broadcast a real-time update to all clients subscribed to a scan.

    Called from agent nodes as they progress through the workflow.

    Args:
        scan_id: The scan UUID
        data: Dict with 'stage', 'message', 'progress', and any extra fields

    Example:
        await broadcast_scan_update(scan_id, {
            "stage": "scanning",
            "message": "Found 12 issues in 5 files",
            "progress": 40
        })
    """
    room = f"scan_{scan_id}"
    payload = {
        "scan_id": scan_id,
        "timestamp": datetime.utcnow().isoformat(),
        "data": data,
    }
    await sio.emit("scan_update", payload, room=room)

    # Also update in-memory store
    if scan_id in active_runs:
        run = active_runs[scan_id]
        run["current_stage"] = data.get("stage", run.get("current_stage"))
        run["progress"] = data.get("progress", run.get("progress", 0))


# ── Core API Endpoints ─────────────────────────────────────────────────────────

@app.get("/", tags=["System"])
async def root():
    """
    API root — shows available endpoints.
    Visit http://localhost:8000 to see this.
    """
    return {
        "name": "PULSE DevOps Agent",
        "tagline": "Pipeline Understanding, Learning & Self-healing Engine",
        "version": settings.APP_VERSION,
        "status": "running",
        "endpoints": {
            "docs":         "/docs",
            "health":       "/health",
            "start_scan":   "POST /api/v1/scans",
            "scan_status":  "GET /api/v1/scans/{scan_id}",
            "scan_results": "GET /api/v1/scans/{scan_id}/results",
            "list_scans":   "GET /api/v1/scans",
        },
        "features": {
            "ai_mode":       settings.active_llm,
            "offline_mode":  settings.OFFLINE_MODE,
            "llm_available": settings.llm_available,
        }
    }


@app.get("/health", response_model=SystemHealthResponse, tags=["System"])
async def health_check():
    """
    System health check.
    Frontend calls this on load to know which features are available.

    Returns:
        - Which analysis tools are installed
        - Which LLM is configured
        - Current version and status

    Expected response when fully set up:
        {
            "status": "healthy",
            "features": {
                "ai_fixes": true,
                "offline_mode": false,
                "llm": "openai",
                "vector_memory": false
            },
            "tools_available": {
                "pylint": true,
                "flake8": true,
                "mypy": false,
                ...
            }
        }
    """
    tools = get_available_tools()

    return SystemHealthResponse(
        status="healthy",
        version=settings.APP_VERSION,
        timestamp=datetime.utcnow(),
        features={
            "ai_fixes":      settings.llm_available,
            "offline_mode":  settings.OFFLINE_MODE or not settings.llm_available,
            "llm":           settings.active_llm,
            "vector_memory": False,    # Phase 4 — not yet implemented
            "github_push":   bool(settings.GITHUB_TOKEN),
            "severity_scoring": True,  # Always available (your unique feature)
            "health_score":  True,     # Always available (your unique feature)
            "rollback":      True,     # Phase 3+
        },
        tools_available=tools,
    )


@app.get("/api/v1/scans", tags=["Scans"])
async def list_scans(page: int = 1, page_size: int = 20):
    """
    List all recent scans (from in-memory store for Phase 1).
    Phase 3+: Will query SQLite database.
    """
    all_runs = list(active_runs.values())
    all_runs.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    start = (page - 1) * page_size
    end = start + page_size
    paginated = all_runs[start:end]

    return {
        "total": len(all_runs),
        "page": page,
        "page_size": page_size,
        "scans": paginated,
    }


@app.get("/api/v1/scans/{scan_id}", tags=["Scans"])
async def get_scan_status(scan_id: str):
    """
    Get current status of a scan.
    Polled by frontend every few seconds until scan completes.
    """
    if scan_id not in active_runs:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found")
    return active_runs[scan_id]


@app.get("/api/v1/scans/{scan_id}/results", tags=["Scans"])
async def get_scan_results(scan_id: str):
    """
    Get complete results of a finished scan.
    Includes issues, fixes, health score, heatmap.
    """
    if scan_id not in active_runs:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found")

    run = active_runs[scan_id]
    if run.get("status") == "running":
        return JSONResponse(
            status_code=202,
            content={"message": "Scan still in progress", "progress": run.get("progress", 0)}
        )

    return run


@app.post("/api/v1/scans/{scan_id}/rollback", tags=["Scans"])
async def rollback_scan(scan_id: str):
    """
    Rollback all fixes from a scan (YOUR UNIQUE FEATURE).
    Implements actual git checkout reset to discard edits.
    """
    if scan_id not in active_runs:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found")

    import subprocess
    import os
    
    repo_dir = os.path.join(os.getcwd(), "cloned_repos", scan_id)
    if os.path.exists(repo_dir):
        try:
            # Run git checkout to discard all changes
            subprocess.run(["git", "checkout", "--", "."], cwd=repo_dir, check=True)
            active_runs[scan_id]["rolled_back"] = True
            
            # Reset all fixed status
            for issue in active_runs[scan_id].get("issues", []):
                issue["fixed"] = False
            active_runs[scan_id]["fixes"] = []
            active_runs[scan_id]["total_fixes_applied"] = 0
            
            return {"message": "Rollback successful. All changes discarded.", "status": "rolled_back"}
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            raise HTTPException(status_code=500, detail=f"Rollback failed: {e}")
    else:
        # If in-memory, just mark
        active_runs[scan_id]["rolled_back"] = True
        return {"message": f"Rollback initiated for scan {scan_id}", "status": "rolled_back"}


# ── Background Task for Scanner Agent ──────────────────────────────────────────
async def run_scanner_background(scan_id: str, repo_url: str, branch_name: str):
    """
    Asynchronous worker that runs the repository scan.
    Runs in the background so the REST API call returns immediately.
    """
    from agents.scanner import ScannerAgent
    
    run_data = active_runs.get(scan_id)
    if not run_data:
        logger.error("Scan run data not found in store", scan_id=scan_id)
        return

    logger.info("Starting background scan task", scan_id=scan_id, repo=repo_url)
    run_data["status"] = "running"
    run_data["started_at"] = datetime.utcnow().isoformat()

    async def on_progress(stage: str, progress: int, message: str):
        logger.info(f"Scan progress [{progress}%]: {message}", scan_id=scan_id, stage=stage)
        await broadcast_scan_update(scan_id, {
            "stage": stage,
            "progress": progress,
            "message": message,
            "status": "running"
        })

    try:
        agent = ScannerAgent(scan_id=scan_id, repo_url=repo_url, branch_name=branch_name)
        results = await agent.execute_scan(on_progress=on_progress)

        # Update run data with results
        run_data["status"] = results.get("status", "success")
        run_data["completed_at"] = datetime.utcnow().isoformat()
        
        try:
            started = datetime.fromisoformat(run_data["started_at"])
            completed = datetime.fromisoformat(run_data["completed_at"])
            run_data["duration_seconds"] = round((completed - started).total_seconds(), 2)
        except Exception:
            run_data["duration_seconds"] = 0.0

        # Map parsed issues to standard IssueResponse schema and frontend compatibility
        mapped_issues = []
        for idx, raw in enumerate(results.get("issues", [])):
            mapped_issues.append({
                "id": f"issue_{scan_id[:8]}_{idx}",
                "file_path": raw.get("file_path"),
                "line": raw.get("line"),
                "line_number": raw.get("line"),
                "column": raw.get("column", 0),
                "column_number": raw.get("column", 0),
                "bug_type": raw.get("bug_type"),
                "severity": raw.get("severity"),
                "severity_score": raw.get("severity_score"),
                "message": raw.get("message"),
                "code_snippet": raw.get("code_snippet", ""),
                "reasoning": raw.get("reasoning", ""),
                "source": raw.get("source"),
                "fixed": False,
                "symbol": ""
            })

        run_data["issues"] = mapped_issues
        run_data["total_issues_found"] = len(mapped_issues)

        # Set health score breakdown
        metrics = results.get("metrics", {})
        run_data["health_score"] = {
            "score": results.get("health_score", 100.0),
            "grade": metrics.get("grade", "A"),
            "label": metrics.get("label", "Excellent"),
            "total_issues": len(mapped_issues),
            "critical_count": metrics.get("critical_count", 0),
            "high_count": metrics.get("high_count", 0),
            "medium_count": metrics.get("medium_count", 0),
            "low_count": metrics.get("low_count", 0),
            "info_count": metrics.get("info_count", 0),
            "top_problem_files": metrics.get("top_problem_files", [])
        }

        # Build dynamic bug heatmap for frontend
        heatmap = {}
        for issue in mapped_issues:
            fp = issue["file_path"]
            heatmap[fp] = heatmap.get(fp, 0) + 1
        run_data["bug_heatmap"] = heatmap

        # Build simple file tree representation for the frontend visualization
        file_tree = {"name": run_data["repository_name"], "isDir": True, "children": []}
        # Group issues and files
        files_added = {}
        for issue in mapped_issues:
            fp = issue["file_path"]
            if fp not in files_added:
                files_added[fp] = True
                parts = fp.split("/")
                current = file_tree
                for i, part in enumerate(parts):
                    is_last = i == len(parts) - 1
                    # Find if child exists
                    existing = next((c for c in current.get("children", []) if c["name"] == part), None)
                    if not existing:
                        new_child = {"name": part, "isDir": not is_last}
                        if not is_last:
                            new_child["children"] = []
                        if "children" not in current:
                            current["children"] = []
                        current["children"].append(new_child)
                        existing = new_child
                    current = existing
        run_data["file_tree"] = file_tree

        # Broadcast scan completion
        await broadcast_scan_update(scan_id, {
            "stage": "completed" if run_data["status"] == "success" else "failed",
            "progress": 100,
            "message": f"Scan completed successfully! Health score: {run_data['health_score']['score']}/100" if run_data["status"] == "success" else f"Scan failed: {run_data['error_message']}",
            "status": run_data["status"],
            "health_score": run_data["health_score"],
            "total_issues_found": run_data["total_issues_found"]
        })

        logger.info("Background scan task completed successfully", scan_id=scan_id, status=run_data["status"])

    except Exception as e:
        logger.exception("Background scan task failed due to unexpected error", scan_id=scan_id)
        run_data["status"] = "failed"
        run_data["completed_at"] = datetime.utcnow().isoformat()
        run_data["error_message"] = str(e)
        
        await broadcast_scan_update(scan_id, {
            "stage": "failed",
            "progress": 100,
            "message": f"Scan encountered an unexpected error: {str(e)}",
            "status": "failed"
        })


@app.post("/api/v1/scans", response_model=ScanStartedResponse, tags=["Scans"])
async def start_scan(request: StartScanRequest, background_tasks: BackgroundTasks):
    """
    Start a new repository scan.
    Triggers the cross-platform static analysis (ScannerAgent) in a background worker task.
    Updates are streamed to frontend in real-time via Socket.IO events.
    """
    repo_url = request.repository_url
    scan_id = str(uuid.uuid4())
    author = request.author_name

    # Extract repo name from URL safely
    repo_name = repo_url.rstrip("/").split("/")[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]

    # Target branch name
    branch_name = request.branch_name or f"pulse-fix-{scan_id[:8]}"

    # Initialize in-memory run state
    run_data = {
        "scan_id": scan_id,
        "status": "pending",
        "current_stage": "initializing",
        "progress": 0,
        "repository_url": repo_url,
        "repository_name": repo_name,
        "author_name": author,
        "branch_name": branch_name,
        "created_at": datetime.utcnow().isoformat(),
        "started_at": None,
        "completed_at": None,
        "total_issues_found": 0,
        "total_fixes_applied": 0,
        "total_fixes_failed": 0,
        "health_score": None,
        "ai_confidence_score": None,
        "issues": [],
        "fixes": [],
        "error_message": None,
        "pull_request_url": None,
        "commit_sha": None,
        "rolled_back": False,
        "enable_ai_fixes": request.enable_ai_fixes,
        "offline_mode": request.offline_mode,
    }

    active_runs[scan_id] = run_data

    # Queue background task to clone & scan the repository
    background_tasks.add_task(run_scanner_background, scan_id, repo_url, branch_name)

    logger.info("Scan queued in background", scan_id=scan_id, repo=repo_url, author=author)

    return ScanStartedResponse(
        scan_id=scan_id,
        status="pending",
        message="Repository scan successfully queued in background.",
        repository_url=repo_url,
        branch_name=branch_name
    )


@app.post("/api/v1/scans/{scan_id}/fix", tags=["Scans"])
async def fix_issue(scan_id: str, request: FixIssueRequest, background_tasks: BackgroundTasks):
    """
    Trigger the Healer Agent to fix a specific issue in the scan.
    """
    if scan_id not in active_runs:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found")

    run_data = active_runs[scan_id]
    
    # Find the issue
    target_issue = None
    for issue in run_data.get("issues", []):
        if issue["id"] == request.issue_id:
            target_issue = issue
            break
            
    if not target_issue:
        raise HTTPException(status_code=404, detail=f"Issue {request.issue_id} not found in scan")
        
    if target_issue.get("fixed"):
        return {"message": "Issue is already fixed", "status": "already_fixed"}

    # Define background task
    async def run_healer_background(scan_id: str, repo_name: str, issue: dict):
        from agents.healer import HealerAgent
        import os
        
        repo_dir = os.path.join(os.getcwd(), "cloned_repos", scan_id)
        
        await broadcast_scan_update(scan_id, {
            "stage": "healing",
            "progress": 50,
            "message": f"AI Healer is analyzing issue in {issue['file_path']}...",
            "status": "running"
        })
        
        healer = HealerAgent()
        fix_data = await healer.generate_fix(repo_dir, issue)
        
        if not fix_data:
            await broadcast_scan_update(scan_id, {
                "stage": "healing_failed",
                "progress": 100,
                "message": f"Failed to generate fix for {issue['file_path']}",
                "status": "success"  # Scan as a whole is still success
            })
            return
            
        applied = await healer.apply_fix(repo_dir, issue, fix_data)
        if applied:
            issue["fixed"] = True
            
            # Save fix record
            fix_record = {
                "id": f"fix_{uuid.uuid4().hex[:8]}",
                "file_path": issue["file_path"],
                "bug_type": issue["bug_type"],
                "description": fix_data.get("explanation", "AI applied fix"),
                "before_code": fix_data.get("before_code", ""),
                "after_code": fix_data.get("after_code", ""),
                "line_number": issue["line_number"],
                "fix_strategy": fix_data.get("engine", "unknown"),
                "ai_confidence": 0.95 if fix_data.get("engine") in ["openai", "gemini"] else 1.0,
                "status": "applied"
            }
            if "fixes" not in run_data:
                run_data["fixes"] = []
            run_data["fixes"].append(fix_record)
            run_data["total_fixes_applied"] += 1
            
            await broadcast_scan_update(scan_id, {
                "stage": "healed",
                "progress": 100,
                "message": f"Successfully fixed issue in {issue['file_path']}",
                "status": "success",
                "fix": fix_record
            })
        else:
            run_data["total_fixes_failed"] += 1
            await broadcast_scan_update(scan_id, {
                "stage": "healing_failed",
                "progress": 100,
                "message": f"Generated fix failed validation or application for {issue['file_path']}",
                "status": "success"
            })

    background_tasks.add_task(run_healer_background, scan_id, run_data.get("repository_name", ""), target_issue)
    
    return {"message": "Fix task queued", "status": "healing"}


# ── Error Handlers ─────────────────────────────────────────────────────────────

@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"error": "Not found", "detail": str(exc.detail)}
    )


@app.exception_handler(500)
async def server_error_handler(request, exc):
    logger.error("Unhandled server error", error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": "Check backend logs"}
    )


# ── Dev Runner ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    # Run with: python main.py
    # But prefer: uvicorn main:socket_app --reload
    uvicorn.run(
        "main:socket_app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
    )

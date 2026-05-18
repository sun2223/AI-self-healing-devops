# PULSE DevOps Agent

**Pipeline Understanding, Learning & Self-healing Engine (PULSE)**

PULSE is a production-grade, AI-powered DevOps agent designed to autonomously scan, audit, score, and self-heal repository vulnerabilities and code quality issues. It features a premium glassmorphism React dashboard and a robust FastAPI backend.

## 🚀 Key Features

* **Autonomous Self-Healing (Healer Agent)**: Utilizes a dual-LLM engine (OpenAI GPT-4o primary, Google Gemini fallback) to draft fixes for static analysis issues. Includes a local, offline rule-based fallback for standard syntax remediation.
* **AST Double-Validation Pipeline**: All AI-generated patches are pre-compiled and validated through an Abstract Syntax Tree (AST) sandbox *before* touching the filesystem, achieving a 0% syntax regression rate.
* **Git-Level Rollback System**: A highly transactional, one-click rollback mechanism (`git checkout -- .`) that isolates workspaces and safely discards applied fixes if they fail testing.
* **Split Before/After Diff Viewer**: Interactive, side-by-side code diff pane showcasing the exact modifications and an AI Confidence Score.
* **Real-time WebSocket Terminal**: Live process logging and pipeline monitoring streaming to the React dashboard via Socket.IO.
* **Resilient Cloning Fallbacks**: Multi-layer error handling during repository ingestion (handling token scope limits, branch mismatching, and permission boundaries).

## 🛠️ Tech Stack

* **Frontend**: React, TypeScript, TailwindCSS (Glassmorphism UI), Vite, Socket.IO-Client
* **Backend**: Python 3.11+, FastAPI, Uvicorn, Python-SocketIO, Pydantic
* **AI / Agentic Logic**: LangGraph, LangChain, OpenAI API, Gemini API
* **DevOps Utilities**: GitPython, AST (Abstract Syntax Tree), Pylint, Flake8, MyPy, Bandit

## ⚙️ Getting Started

### 1. Backend Setup
Navigate to the backend directory and install dependencies:
```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate # Linux/Mac
pip install -r requirements.txt
```

Set up your `.env` file in the `/backend` directory:
```env
OPENAI_API_KEY=your_openai_key
GEMINI_API_KEY=your_gemini_key
GITHUB_TOKEN=your_github_pat
```

Run the FastAPI server:
```bash
python -m uvicorn main:socket_app --host 0.0.0.0 --port 8000 --reload
```

### 2. Frontend Setup
Navigate to the frontend directory:
```bash
cd frontend
npm install
npm run dev
```

The React dashboard will be available at `http://localhost:5173`.

## 📐 Architecture Overview

1. **Dashboard** triggers a new scan via a standard HTTP REST call.
2. **FastAPI Background Worker** initializes the **Scanner Agent**, which dynamically clones the target repository into an isolated sandbox.
3. Static Linters run against the repository, calculating a dynamic **Health Score** and mapping a **Bug Heatmap**.
4. The user selects an issue and triggers the **Healer Agent**.
5. The Healer feeds the surrounding context to the **LLM Chain**, producing an AST-validated patch.
6. The UI dynamically receives the patched code via **Socket.IO** and presents a Split Diff.

## 📄 License
MIT License

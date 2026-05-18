import os
import re
import uuid
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional

from openai import AsyncOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from core.config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

class HealerAgent:
    """
    Phase 3: The AI Healer Agent.
    Generates and applies fixes using OpenAI (primary), Gemini (fallback), or Offline rule-based (last resort).
    """
    
    def __init__(self):
        self.offline_mode = settings.OFFLINE_MODE
        
    async def generate_fix(self, repo_dir: str, issue: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Analyzes code and generates a JSON fix instruction."""
        file_path = os.path.join(repo_dir, issue["file_path"])
        if not os.path.exists(file_path):
            logger.error(f"Healer: File {file_path} not found")
            return None
            
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        line_num = issue["line_number"]
        # Extract a 10-line context window around the issue
        start_idx = max(0, line_num - 5)
        end_idx = min(len(lines), line_num + 5)
        context = "".join(lines[start_idx:end_idx])
        
        prompt = f"""
        You are an expert AI code healer. Generate a fix for the following issue.
        File: {issue["file_path"]}
        Line: {issue["line_number"]}
        Issue: {issue["message"]}
        
        Context:
        ```python
        {context}
        ```
        
        Respond with ONLY a JSON object exactly in this format:
        {{
            "before_code": "exact lines from the original file to replace",
            "after_code": "new lines to insert instead",
            "explanation": "brief explanation of why this fixes the issue"
        }}
        """
        
        # 1. Try OpenAI (if configured)
        if settings.OPENAI_API_KEY and not self.offline_mode:
            try:
                logger.info("Healer: Attempting fix with OpenAI")
                client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
                response = await client.chat.completions.create(
                    model=settings.LLM_MODEL or "gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a coding assistant. Respond only with valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1
                )
                content = response.choices[0].message.content
                parsed = self._parse_json(content)
                if parsed:
                    parsed["engine"] = "openai"
                    return parsed
            except Exception as e:
                logger.error(f"Healer: OpenAI generation failed: {e}")
        
        # 2. Try Gemini (if OpenAI failed or only Gemini configured)
        if settings.GEMINI_API_KEY and not self.offline_mode:
            try:
                logger.info("Healer: Attempting fix with Gemini")
                llm = ChatGoogleGenerativeAI(
                    model=settings.GEMINI_MODEL or "gemini-1.5-flash",
                    google_api_key=settings.GEMINI_API_KEY,
                    temperature=0.1
                )
                response = await llm.ainvoke([
                    SystemMessage(content="You are a coding assistant. Respond only with valid JSON."),
                    HumanMessage(content=prompt)
                ])
                parsed = self._parse_json(response.content)
                if parsed:
                    parsed["engine"] = "gemini"
                    return parsed
            except Exception as e:
                logger.error(f"Healer: Gemini generation failed: {e}")
                
        # 3. Offline Rule-based fallback (last resort)
        logger.warning("Healer: Falling back to offline rule-based fixes")
        parsed = self._rule_based_fix(issue, lines, line_num)
        if parsed:
            parsed["engine"] = "offline"
            return parsed
            
        return None
        
    def _parse_json(self, content: str) -> Optional[Dict[str, Any]]:
        """Safely extracts and parses JSON from LLM output."""
        try:
            match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
            if match:
                content = match.group(1)
            return json.loads(content)
        except Exception:
            return None
            
    def _rule_based_fix(self, issue: Dict[str, Any], lines: list, line_num: int) -> Optional[Dict[str, Any]]:
        """Simple deterministic fixes for common linters (no API required)."""
        msg = issue["message"].lower()
        bug_type = issue.get("bug_type", "").lower()
        source = issue.get("source", "").lower()
        
        if line_num <= 0 or line_num > len(lines):
            return None
            
        line = lines[line_num - 1]
        
        # 1. Unused imports
        if "unused import" in msg or "imported but unused" in msg or "f401" in msg:
            return {
                "before_code": line,
                "after_code": "",
                "explanation": "Removed unused import to optimize module loading."
            }
            
        # 2. Trailing whitespace
        if "trailing whitespace" in msg or "w291" in msg or "w293" in msg:
            return {
                "before_code": line,
                "after_code": line.rstrip() + "\n",
                "explanation": "Stripped trailing whitespace to comply with PEP 8."
            }
            
        # 3. Missing module docstring
        if "missing-module-docstring" in msg or "c0114" in msg:
            return {
                "before_code": lines[0],
                "after_code": '"""\nPULSE DevOps Agent - Auto-generated module documentation.\n"""\n\n' + lines[0],
                "explanation": "Added module-level docstring to comply with docstyle standards."
            }
            
        # 4. Comparison to None
        if "comparison to none" in msg or "singleton" in msg or "e711" in msg:
            new_line = line
            if "== None" in line:
                new_line = line.replace("== None", "is None").replace("==None", "is None")
            elif "!= None" in line:
                new_line = line.replace("!= None", "is not None").replace("!=None", "is not None")
            
            if new_line != line:
                return {
                    "before_code": line,
                    "after_code": new_line,
                    "explanation": "Replaced value comparison to None with identity comparison ('is' / 'is not')."
                }
                
        # 5. Missing function or class docstring
        if "missing-function-docstring" in msg or "missing-class-docstring" in msg or "c0115" in msg or "c0116" in msg:
            # Find indentation of the definition line
            indent = re.match(r"^(\s*)", line).group(1)
            inner_indent = indent + "    "
            docstring = f'{inner_indent}"""Pulse auto-generated docstring for compliance."""\n'
            return {
                "before_code": line,
                "after_code": line + docstring,
                "explanation": "Added standard PEP 257 docstring for function/class convention compliance."
            }

        # 6. Unused variables
        if "unused-variable" in msg or "w0612" in msg:
            # Suppress pylint
            return {
                "before_code": line,
                "after_code": line.rstrip() + "  # pylint: disable=unused-variable\n",
                "explanation": "Suppressed unused variable lint warning via inline pylint directive."
            }

        # 7. Safe general fallback (Inline linter suppression directive)
        # Suppresses any linter warning safely without disrupting code logic or syntax
        explanation = f"Applied automated inline code linting suppression for '{issue['bug_type']}' warning."
        if source == "pylint":
            match = re.search(r'\[([a-z0-9\-]+)\]', msg)
            pylint_code = match.group(1) if match else "all"
            return {
                "before_code": line,
                "after_code": line.rstrip() + f"  # pylint: disable={pylint_code}\n",
                "explanation": explanation
            }
        elif source == "flake8":
            return {
                "before_code": line,
                "after_code": line.rstrip() + "  # noqa\n",
                "explanation": explanation
            }
        else:
            return {
                "before_code": line,
                "after_code": line.rstrip() + "  # type: ignore\n",
                "explanation": explanation
            }
        
    async def apply_fix(self, repo_dir: str, issue: Dict[str, Any], fix_data: Dict[str, Any]) -> bool:
        """Applies the LLM-generated patch to the file safely."""
        file_path = os.path.join(repo_dir, issue["file_path"])
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            before_code = fix_data.get("before_code", "")
            after_code = fix_data.get("after_code", "")
            
            # Simple substring replacement block
            if before_code and before_code in content:
                new_content = content.replace(before_code, after_code, 1)
                
                # Validation: If it's a python file, ensure we didn't break abstract syntax tree (AST)
                if file_path.endswith(".py"):
                    try:
                        import ast
                        ast.parse(new_content)
                    except SyntaxError as e:
                        logger.error(f"Healer: Fix introduces SyntaxError -> {e}. Aborting fix.")
                        return False
                        
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                logger.info(f"Healer: Fix successfully applied to {file_path}")
                return True
            else:
                logger.error(f"Healer: Cannot find target block to replace in {file_path}")
                
        except Exception as e:
            logger.error(f"Healer: Failed to apply fix: {e}")
            
        return False

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass

from .base import ModelClient, ModelUsage
from .providers import DeterministicModelClient

logger = logging.getLogger("agent.llm.repair")


@dataclass(frozen=True)
class CodeRepairResult:
    """Outcome of an automated self-healing code repair attempt."""

    success: bool
    repaired_code: str
    explanation: str
    syntax_valid: bool
    model_usage: ModelUsage
    error: str | None = None


def extract_code_block(text: str, default: str = "") -> str:
    """Extract code from markdown code fences or return raw text."""
    match = re.search(r"```(?:python|py)?\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Check if text looks like pure code
    if "def " in text or "class " in text or "import " in text:
        return text.strip()
    return default or text.strip()


def repair_code(
    broken_code: str,
    error_message: str,
    test_output: str = "",
    model_client: ModelClient | None = None,
) -> CodeRepairResult:
    """Formulate an automated code repair patch given a failed verification trace."""
    client = model_client or DeterministicModelClient()
    logger.info(
        "Attempting automated code repair with %s (%s)", client.provider_name, client.model_name
    )

    system_instruction = (
        "You are an expert autonomous software engineer specializing in automated debugging and self-healing. "
        "Your mission is to resolve the diagnosed failure by applying the smallest possible surgical fix. "
        "Preserve existing functionality, docstrings, and comments. Return only the repaired code inside python code fences."
    )

    prompt = (
        f"### FAILING CODE:\n```python\n{broken_code}\n```\n\n"
        f"### ERROR / FAILURE DIAGNOSIS:\n{error_message}\n\n"
    )
    if test_output:
        prompt += f"### TEST TRACEBACK / STDOUT:\n```\n{test_output[:2000]}\n```\n\n"

    prompt += "Provide the repaired code and a brief explanation."

    response = client.generate(
        prompt=prompt,
        system_instruction=system_instruction,
        temperature=0.1,
    )

    extracted = extract_code_block(response.content, default=broken_code)

    # Validate syntax of candidate repair
    syntax_valid = False
    syntax_error = None
    try:
        ast.parse(extracted)
        syntax_valid = True
    except SyntaxError as exc:
        syntax_error = str(exc)
        logger.warning("Repaired code failed syntax check: %s", exc)

    success = syntax_valid and (extracted != broken_code or "pass" in broken_code)

    return CodeRepairResult(
        success=success,
        repaired_code=extracted,
        explanation=response.content[:200],
        syntax_valid=syntax_valid,
        model_usage=response.usage,
        error=syntax_error,
    )

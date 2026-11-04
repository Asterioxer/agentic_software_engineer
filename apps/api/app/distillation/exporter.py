from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..domain import RunStatus
from ..store import RunStore, get_default_store

logger = logging.getLogger("agent.distillation")


class DatasetExporter:
    """Exports verified, deterministic agent execution journals into fine-tuning datasets."""

    def __init__(self, store: RunStore | None = None) -> None:
        self.store = store or get_default_store()

    def extract_training_records(self, limit: int = 1000) -> list[dict[str, Any]]:
        """Extract verified execution runs into standard ChatML fine-tuning records."""
        runs_summary = self.store.list_runs(limit=limit)
        records: list[dict[str, Any]] = []

        for r_meta in runs_summary:
            run_id = r_meta.get("run_id")
            if not run_id:
                continue

            checkpoint = self.store.get_checkpoint(run_id)
            if not checkpoint or checkpoint.status != RunStatus.COMPLETED:
                continue

            # Only distill runs with 100% verified passing checks
            if not checkpoint.verification or not all(v.passed for v in checkpoint.verification):
                continue

            # Format ChatML conversation pair
            sys_msg = (
                "You are an expert autonomous software engineer. "
                "Given a software engineering task, formulate a structured execution plan, "
                "generate surgical patches, and ensure independent verification criteria pass."
            )

            user_msg = (
                f"Task: {checkpoint.task.title}\n\nDescription:\n{checkpoint.task.description}\n"
            )
            if checkpoint.task.repository:
                user_msg += f"\nRepository: {checkpoint.task.repository}"

            # Assistant response distillation
            assistant_parts: list[str] = ["### Execution Plan:"]
            for step in checkpoint.plan:
                tool_label = f" (tool: {step.tool})" if step.tool else ""
                assistant_parts.append(f"- [{step.id}]{tool_label}: {step.description}")

            # Include operations
            ops = self.store.list_operations_for_run(run_id)
            if ops:
                assistant_parts.append("\n### Applied Operations:")
                for op in ops:
                    assistant_parts.append(
                        f"- Operation {op.operation_id} [{op.tool}]: state={op.state.value}"
                    )

            assistant_parts.append("\n### Verification Evidence:")
            for v in checkpoint.verification:
                assistant_parts.append(f"- [PASS] {v.check}: {v.detail}")

            asst_msg = "\n".join(assistant_parts)

            records.append(
                {
                    "messages": [
                        {"role": "system", "content": sys_msg},
                        {"role": "user", "content": user_msg},
                        {"role": "assistant", "content": asst_msg},
                    ],
                    "metadata": {
                        "run_id": run_id,
                        "task_title": checkpoint.task.title,
                        "verification_checks_passed": len(checkpoint.verification),
                        "operations_count": len(ops),
                    },
                }
            )

        logger.info("Extracted %d verified training pairs from operation journal", len(records))
        return records

    def export_to_jsonl(self, output_path: str | Path, limit: int = 1000) -> int:
        """Write extracted training records to a JSONL dataset file."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        records = self.extract_training_records(limit=limit)
        with open(out, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(rec) + "\n" for rec in records)

        return len(records)

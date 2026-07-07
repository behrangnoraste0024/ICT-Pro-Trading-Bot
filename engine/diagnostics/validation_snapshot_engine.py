from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.multi_sample_validation import MultiSampleValidationResult
from models.validation_snapshot import ValidationSnapshot, ValidationSnapshotMetadata


class ValidationSnapshotEngine:
    SNAPSHOT_SCHEMA_VERSION = "2.50.0"

    def build_snapshot(
        self,
        result: MultiSampleValidationResult,
        strategy_set: str,
        sort_by: str,
        recommended_profile: str | None,
        cache_enabled: bool,
        cache_dir: str | None,
        max_windows: int | None,
        fast: bool,
        command: str | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> ValidationSnapshot:
        metadata = ValidationSnapshotMetadata(
            snapshot_schema_version=self.SNAPSHOT_SCHEMA_VERSION,
            created_at=self._created_at(),
            git_commit=self._git_value(["git", "rev-parse", "--short", "HEAD"]),
            git_branch=self._git_value(["git", "branch", "--show-current"]),
            command=command,
            strategy_set=strategy_set,
            sort_by=sort_by,
            recommended_profile=recommended_profile,
            cache_enabled=cache_enabled,
            cache_dir=cache_dir,
            max_windows=max_windows,
            fast=fast,
        )
        return ValidationSnapshot(
            metadata=metadata,
            multi_sample_result=result,
            diagnostics=diagnostics or {},
        )

    def export(
        self,
        snapshot: ValidationSnapshot,
        output_dir: str,
        snapshot_format: str = "both",
    ) -> list[str]:
        if snapshot_format not in ("json", "md", "both"):
            raise ValueError(f"unsupported snapshot format: {snapshot_format}")
        paths: list[str] = []
        if snapshot_format in ("json", "both"):
            paths.append(self.export_json(snapshot, output_dir))
        if snapshot_format in ("md", "both"):
            paths.append(self.export_markdown(snapshot, output_dir))
        return paths

    def export_json(self, snapshot: ValidationSnapshot, output_dir: str) -> str:
        path = self._output_path(snapshot, output_dir, "json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot.to_dict(), indent=2), encoding="utf-8")
        return str(path)

    def export_markdown(self, snapshot: ValidationSnapshot, output_dir: str) -> str:
        path = self._output_path(snapshot, output_dir, "md")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render_markdown(snapshot), encoding="utf-8")
        return str(path)

    def render_markdown(self, snapshot: ValidationSnapshot) -> str:
        metadata = snapshot.metadata
        result = snapshot.multi_sample_result
        lines = [
            "# Validation Snapshot",
            "",
            "## Metadata",
            f"- Created At: {metadata.created_at}",
            f"- Git Commit: {metadata.git_commit}",
            f"- Git Branch: {metadata.git_branch}",
            f"- Strategy Set: {metadata.strategy_set}",
            f"- Sort By: {metadata.sort_by}",
            f"- Recommended Profile: {metadata.recommended_profile}",
            f"- Cache Enabled: {metadata.cache_enabled}",
            f"- Cache Dir: {metadata.cache_dir}",
            f"- Max Windows: {metadata.max_windows}",
            f"- Fast: {metadata.fast}",
            "",
            "## Summary",
            f"- Total Samples: {result.total_samples}",
            f"- Completed Samples: {result.completed_samples}",
            f"- Passed Samples: {result.passed_samples}",
            f"- Warning Samples: {result.warning_samples}",
            f"- Failed Samples: {result.failed_samples}",
            f"- Skipped Samples: {result.skipped_samples}",
            f"- Error Samples: {result.error_samples}",
            "",
            "## Samples",
            "",
            "| Sample | Symbol | TF | Status | Profile | ScoreThr | Trades | W/L | Win% | NetAfterCost | MaxDD | WFStatus | ProfSeg | LosingSeg | EmptySeg | WorstSegNet | ImproveVsBase | Cache | CacheRead | OrigElapsed | SavedEst | CacheAge | Error |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in result.rows:
            lines.append(
                f"| {row.sample_name} | {row.symbol} | {row.timeframe} | {row.status} | "
                f"{row.recommended_profile} | {self._fmt(row.score_threshold)} | {row.total_trades} | "
                f"{row.wins}/{row.losses} | {self._fmt(row.win_rate)} | {self._fmt(row.net_pnl_after_costs)} | "
                f"{self._fmt(row.max_drawdown)} | {row.validation_status} | {self._fmt(row.profitable_segments)} | "
                f"{self._fmt(row.losing_segments)} | {self._fmt(row.empty_segments)} | "
                f"{self._fmt(row.worst_segment_net_pnl_after_costs)} | {self._fmt(row.improvement_vs_baseline)} | "
                f"{row.cache_status} | {self._fmt(row.cache_read_elapsed_seconds)} | "
                f"{self._fmt(row.original_elapsed_seconds)} | {self._fmt(row.estimated_saved_seconds)} | "
                f"{self._fmt(row.cache_age_seconds)} | {row.error_message} |"
            )
        lines.extend(
            [
                "",
                "## Notes",
                "- This snapshot is research/audit output only.",
                "- It does not imply live trading approval.",
            ]
        )
        return "\n".join(lines)

    def filename(self, snapshot: ValidationSnapshot, extension: str) -> str:
        created_at = snapshot.metadata.created_at
        timestamp = self._timestamp_for_filename(created_at)
        commit = self._sanitize(snapshot.metadata.git_commit or "unknown")
        profile = self._sanitize(snapshot.metadata.recommended_profile or "unknown")
        return f"validation_snapshot_{timestamp}_{commit}_{profile}.{extension}"

    def _output_path(self, snapshot: ValidationSnapshot, output_dir: str, extension: str) -> Path:
        return Path(output_dir) / self.filename(snapshot, extension)

    def _created_at(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _timestamp_for_filename(self, created_at: str) -> str:
        try:
            parsed = datetime.fromisoformat(created_at)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            parsed = parsed.astimezone(timezone.utc)
        except ValueError:
            parsed = datetime.now(timezone.utc)
        return parsed.strftime("%Y%m%dT%H%M%SZ")

    def _git_value(self, command: list[str]) -> str | None:
        try:
            completed = subprocess.run(command, check=True, capture_output=True, text=True)
            value = completed.stdout.strip()
            return value or None
        except Exception:
            return None

    def _sanitize(self, value: str) -> str:
        sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
        return sanitized.strip("._-") or "unknown"

    def _fmt(self, value) -> str:
        if value is None:
            return "None"
        if isinstance(value, (float, int)):
            return f"{value:.2f}"
        return str(value)

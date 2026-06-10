from __future__ import annotations
from app.models import PipelineResult, PipelineSummary, Status, GatewayConfig
from app.teleport.adapter import TeleportAdapter, TeleportError
from app.checks.postgres import run_batch


def run(gw: GatewayConfig, teleport: TeleportAdapter) -> PipelineResult:
    result = PipelineResult()
    summary = PipelineSummary()

    try:
        raw = run_batch(gw, teleport)
        sections = _split_sections(raw)
        _parse_last_task(summary, sections.get("LAST_TASK", ""))
        _parse_image_summary(summary, sections.get("IMAGE_SUMMARY", ""))
        _parse_images_recent(summary, sections.get("IMAGES_RECENT", ""))
        _parse_tasks_recent(summary, sections.get("TASKS_RECENT", ""))
        _parse_backlog(summary, sections.get("BACKLOG", ""))
        summary.backlog_by_type = _parse_table(sections.get("BACKLOG_BY_TYPE", ""))
        summary.failed_by_type = _parse_table(sections.get("FAILED_BY_TYPE", ""))
        summary.failed_last_24h = _parse_table(sections.get("FAILED_24H", ""))
        summary.processed_by_type_15m = _parse_table(sections.get("PROCESSED_15M", ""))
        summary.task_status_counts = _parse_table(sections.get("TASK_STATUS_COUNTS", ""))
        summary.study_processing_status = _parse_table(sections.get("STUDY_STATUS", ""))
        summary.series_processing_status = _parse_table(sections.get("SERIES_STATUS", ""))
        _parse_sc_publish_24h(summary, sections.get("SC_PUBLISH_24H", ""))
    except TeleportError as e:
        result.error = str(e)
        result.status = Status.WARNING
        result.summary = summary
        return result

    result.summary = summary
    result.status = _compute_status(summary)
    return result


def _split_sections(output: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current_key = None
    current_lines: list[str] = []

    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("---") and stripped.endswith("---"):
            if current_key is not None:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key = stripped.strip("-")
            current_lines = []
        else:
            current_lines.append(line)

    if current_key is not None:
        sections[current_key] = "\n".join(current_lines).strip()

    return sections


def _first_row(output: str) -> list[str]:
    for line in output.strip().splitlines():
        if line.strip():
            return line.split("|")
    return []


def _parse_table(output: str) -> list[dict]:
    rows = []
    for line in output.strip().splitlines():
        if line.strip():
            rows.append({"values": line.split("|")})
    return rows


def _int(val: str) -> int | None:
    try:
        return int(val.strip())
    except (ValueError, AttributeError):
        return None


def _parse_last_task(summary: PipelineSummary, output: str) -> None:
    val = output.strip()
    summary.last_successful_task_at = val if val else None


def _parse_image_summary(summary: PipelineSummary, output: str) -> None:
    row = _first_row(output)
    if len(row) >= 3:
        summary.last_image_created_at = row[0].strip() or None
        summary.last_image_updated_at = row[1].strip() or None
        summary.not_uploaded_to_cloud = _int(row[2])


def _parse_images_recent(summary: PipelineSummary, output: str) -> None:
    row = _first_row(output)
    if len(row) >= 3:
        summary.images_last_5m = _int(row[0])
        summary.images_last_15m = _int(row[1])
        summary.images_updated_last_5m = _int(row[2])
    if len(row) >= 4:
        summary.images_last_24h = _int(row[3])


def _parse_sc_publish_24h(summary: PipelineSummary, output: str) -> None:
    row = _first_row(output)
    if row:
        summary.sc_published_24h = _int(row[0])


def _parse_tasks_recent(summary: PipelineSummary, output: str) -> None:
    row = _first_row(output)
    if len(row) >= 3:
        summary.pending_created_15m = _int(row[0])
        summary.processed_15m = _int(row[1])
        summary.failed_15m = _int(row[2])


def _parse_backlog(summary: PipelineSummary, output: str) -> None:
    row = _first_row(output)
    if len(row) >= 3:
        summary.pending_total = _int(row[0])
        summary.pending_older_30m = _int(row[1])
        summary.pending_older_2h = _int(row[2])


def _compute_status(s: PipelineSummary) -> Status:
    if s.images_last_15m and s.processed_15m == 0:
        return Status.CRITICAL
    if s.failed_15m and s.failed_15m > 0:
        return Status.WARNING
    if s.pending_older_2h and s.pending_older_2h > 0:
        return Status.WARNING
    if s.processed_15m and s.processed_15m > 0 and not s.failed_15m:
        return Status.OK
    return Status.OK

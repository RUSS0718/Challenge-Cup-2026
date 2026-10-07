"""Schema and validator for the offline reviewed-error notebook."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping


NOTEBOOK_VERSION = 1
MAX_ENTRY_CHARS = 8_000
MAX_TEXT_CHARS = 1_200
MAX_SOURCE_IDS = 16
MAX_TAGS = 8
_ENTRY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_STATUSES = frozenset({"draft", "reviewed", "validated", "rejected"})
_REQUIRED_FIELDS = frozenset(
    {
        "entry_id",
        "pattern",
        "domain",
        "mistake",
        "corrective_rule",
        "use_when",
        "do_not_use",
        "source_trace_ids",
        "validation",
    }
)
_OPTIONAL_FIELDS = frozenset({"tags", "skill_name", "reviewer", "notes", "version"})
_FORBIDDEN_FIELDS = frozenset(
    {
        "answer",
        "answers",
        "gold",
        "gold_answer",
        "reference_answer",
        "solution",
        "reference_solution",
        "raw_response",
        "raw_prompt",
        "full_prompt",
        "prompt",
        "response",
        "problem",
        "raw_problem",
        "problem_text",
        "hidden_answer",
    }
)


@dataclass(frozen=True)
class ValidationIssue:
    line: int
    code: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NotebookEntry:
    """A reviewed, generalised mistake pattern without raw answer data."""

    entry_id: str
    pattern: str
    domain: str
    mistake: str
    corrective_rule: str
    use_when: str
    do_not_use: str
    source_trace_ids: tuple[str, ...]
    validation_status: str
    held_out_total: int = 0
    held_out_pass: int = 0
    tags: tuple[str, ...] = ()
    skill_name: str = ""
    reviewer: str = ""
    notes: str = ""
    version: int = NOTEBOOK_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "pattern": self.pattern,
            "domain": self.domain,
            "mistake": self.mistake,
            "corrective_rule": self.corrective_rule,
            "use_when": self.use_when,
            "do_not_use": self.do_not_use,
            "source_trace_ids": list(self.source_trace_ids),
            "validation": {
                "status": self.validation_status,
                "held_out_total": self.held_out_total,
                "held_out_pass": self.held_out_pass,
            },
            "tags": list(self.tags),
            "skill_name": self.skill_name,
            "reviewer": self.reviewer,
            "notes": self.notes,
            "version": self.version,
        }


@dataclass(frozen=True)
class NotebookValidationReport:
    path: str
    entry_count: int
    issues: tuple[ValidationIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "entry_count": self.entry_count,
            "valid": self.valid,
            "issues": [issue.as_dict() for issue in self.issues],
        }


def _bounded_text(value: Any, field: str, issues: list[ValidationIssue], line: int) -> str:
    if not isinstance(value, str) or not value.strip():
        issues.append(ValidationIssue(line, f"{field}_invalid", f"{field} must be a non-empty string"))
        return ""
    text = value.strip()
    if len(text) > MAX_TEXT_CHARS:
        issues.append(ValidationIssue(line, f"{field}_too_long", f"{field} exceeds {MAX_TEXT_CHARS} characters"))
    if "\x00" in text or "\n" in text or "\r" in text:
        issues.append(ValidationIssue(line, f"{field}_control", f"{field} must be a single line without controls"))
    return text[:MAX_TEXT_CHARS]


def validate_notebook_entry(row: Mapping[str, Any], *, line: int = 1) -> list[ValidationIssue]:
    """Validate one JSON object and return bounded, actionable issues."""

    issues: list[ValidationIssue] = []
    if not isinstance(row, Mapping):
        return [ValidationIssue(line, "entry_type", "entry must be a JSON object")]
    try:
        encoded_length = len(json.dumps(dict(row), ensure_ascii=False, separators=(",", ":")))
    except (TypeError, ValueError):
        encoded_length = MAX_ENTRY_CHARS + 1
    if encoded_length > MAX_ENTRY_CHARS:
        issues.append(ValidationIssue(line, "entry_too_large", f"entry exceeds {MAX_ENTRY_CHARS} characters"))

    keys = {str(key) for key in row}
    for key in sorted(keys & _FORBIDDEN_FIELDS):
        issues.append(ValidationIssue(line, "forbidden_field", f"field {key!r} is not allowed in offline notebook"))
    unknown = keys - _REQUIRED_FIELDS - _OPTIONAL_FIELDS - _FORBIDDEN_FIELDS
    if unknown:
        issues.append(ValidationIssue(line, "unknown_field", "unknown fields are not allowed"))
    missing = _REQUIRED_FIELDS - keys
    if missing:
        issues.append(ValidationIssue(line, "missing_field", "missing: " + ",".join(sorted(missing))))

    entry_id = row.get("entry_id")
    if not isinstance(entry_id, str) or not _ENTRY_ID_RE.fullmatch(entry_id.strip()):
        issues.append(ValidationIssue(line, "entry_id_invalid", "entry_id must match [a-z0-9][a-z0-9_-]{0,63}"))
    for field in ("pattern", "domain", "mistake", "corrective_rule", "use_when", "do_not_use"):
        _bounded_text(row.get(field), field, issues, line)

    source_ids = row.get("source_trace_ids")
    if not isinstance(source_ids, list) or not source_ids or len(source_ids) > MAX_SOURCE_IDS:
        issues.append(ValidationIssue(line, "source_trace_ids_invalid", "source_trace_ids must contain 1-16 ids"))
    else:
        for source_id in source_ids:
            if not isinstance(source_id, str) or not source_id.strip() or len(source_id.strip()) > 128 or "\n" in source_id:
                issues.append(ValidationIssue(line, "source_trace_id_invalid", "source trace ids must be bounded strings"))

    validation = row.get("validation")
    if not isinstance(validation, Mapping):
        issues.append(ValidationIssue(line, "validation_invalid", "validation must be an object"))
    else:
        status = validation.get("status")
        if status not in _STATUSES:
            issues.append(ValidationIssue(line, "validation_status_invalid", "validation.status is not recognised"))
        total = validation.get("held_out_total", 0)
        passed = validation.get("held_out_pass", 0)
        if not isinstance(total, int) or isinstance(total, bool) or total < 0:
            issues.append(ValidationIssue(line, "held_out_total_invalid", "held_out_total must be a non-negative integer"))
            total = 0
        if not isinstance(passed, int) or isinstance(passed, bool) or passed < 0 or passed > total:
            issues.append(ValidationIssue(line, "held_out_pass_invalid", "held_out_pass must satisfy 0 <= pass <= total"))
        if status == "validated" and total < 1:
            issues.append(ValidationIssue(line, "validated_without_holdout", "validated entries require held-out cases"))

    tags = row.get("tags", [])
    if not isinstance(tags, list) or len(tags) > MAX_TAGS or any(not isinstance(tag, str) or not tag.strip() for tag in tags):
        issues.append(ValidationIssue(line, "tags_invalid", "tags must be at most 8 non-empty strings"))
    skill_name = row.get("skill_name", "")
    if skill_name and (not isinstance(skill_name, str) or not _SKILL_NAME_RE.fullmatch(skill_name)):
        issues.append(ValidationIssue(line, "skill_name_invalid", "skill_name must be a lowercase hyphenated name"))
    for field in ("reviewer", "notes"):
        if field in row and row[field] not in (None, ""):
            _bounded_text(row[field], field, issues, line)
    version = row.get("version", NOTEBOOK_VERSION)
    if version != NOTEBOOK_VERSION:
        issues.append(ValidationIssue(line, "version_invalid", f"version must be {NOTEBOOK_VERSION}"))
    return issues


def validate_notebook_rows(rows: Iterable[Mapping[str, Any]]) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []
    seen: set[str] = set()
    for line, row in enumerate(rows, start=1):
        issues.extend(validate_notebook_entry(row, line=line))
        entry_id = row.get("entry_id") if isinstance(row, Mapping) else None
        if isinstance(entry_id, str) and entry_id in seen:
            issues.append(ValidationIssue(line, "duplicate_entry_id", f"duplicate entry_id {entry_id!r}"))
        elif isinstance(entry_id, str):
            seen.add(entry_id)
    return tuple(issues)


def validate_notebook_file(path: str | Path) -> NotebookValidationReport:
    """Validate a JSONL notebook without loading raw model traces."""

    file_path = Path(path)
    issues: list[ValidationIssue] = []
    rows: list[tuple[int, Mapping[str, Any]]] = []
    try:
        with file_path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                if not raw_line.strip():
                    continue
                try:
                    value = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    issues.append(ValidationIssue(line_number, "json_invalid", f"invalid JSON at column {exc.colno}"))
                    continue
                rows.append((line_number, value if isinstance(value, Mapping) else {}))
                issues.extend(validate_notebook_entry(value, line=line_number))
    except OSError as exc:
        issues.append(ValidationIssue(0, "file_error", str(exc)[:160]))
    # validate_notebook_entry already checks all rows; this pass adds duplicate
    # detection while keeping line numbers from the source file.
    seen: set[str] = set()
    for line_number, row in rows:
        entry_id = row.get("entry_id")
        if isinstance(entry_id, str):
            if entry_id in seen:
                issues.append(
                    ValidationIssue(
                        line_number,
                        "duplicate_entry_id",
                        f"duplicate entry_id {entry_id!r}",
                    )
                )
            seen.add(entry_id)
    return NotebookValidationReport(str(file_path), len(rows), tuple(issues))


__all__ = [
    "NOTEBOOK_VERSION",
    "NotebookEntry",
    "NotebookValidationReport",
    "ValidationIssue",
    "validate_notebook_entry",
    "validate_notebook_file",
    "validate_notebook_rows",
]

"""Offline reviewed-error notebook.

The package validates human-reviewed JSONL entries only.  ``user_agent`` does
not import it, so solving a question never writes or retrieves notebook data.
"""

from .schema import (
    NotebookEntry,
    NotebookValidationReport,
    ValidationIssue,
    validate_notebook_file,
    validate_notebook_rows,
)

__all__ = [
    "NotebookEntry",
    "NotebookValidationReport",
    "ValidationIssue",
    "validate_notebook_file",
    "validate_notebook_rows",
]

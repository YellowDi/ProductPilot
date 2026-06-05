"""Task state model for listing automation."""

from __future__ import annotations

from enum import StrEnum


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    FAILED = "failed"
    COMPLETED = "completed"


class WorkflowStep(StrEnum):
    IMPORTED = "imported"
    VALIDATED = "validated"
    LOGIN_CHECKED = "login_checked"
    OPENED_CREATE_PAGE = "opened_create_page"
    SELECTED_CATEGORY = "selected_category"
    FILLED_BASIC_INFO = "filled_basic_info"
    UPLOADED_IMAGES = "uploaded_images"
    FILLED_SKUS = "filled_skus"
    FILLED_LOGISTICS = "filled_logistics"
    SAVED_DRAFT = "saved_draft"
    MANUAL_PUBLISH_REQUIRED = "manual_publish_required"

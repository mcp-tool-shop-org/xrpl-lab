"""Canonical API response schemas -- single source of truth.

These models define the API contract between backend and frontend.
Routes MUST return instances of these models.
Frontend TypeScript types MUST mirror these fields exactly.
Contract tests validate both sides against these definitions.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# -- /api/status -----------------------------------------------------------


class LastRun(BaseModel):
    module: str
    timestamp: str
    success: bool


class StatusResponse(BaseModel):
    modules_completed: int
    modules_total: int
    wallet_configured: bool
    wallet_address: str | None
    last_run: LastRun | None
    workspace: str


# -- /api/modules ----------------------------------------------------------


class ModuleSummary(BaseModel):
    id: str
    title: str
    track: str = ""
    summary: str = ""
    level: str
    time_estimate: str
    mode: str = "testnet"
    requires: list[str] = Field(default_factory=list)
    produces: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)
    completed: bool
    is_next: bool = False


class ModuleDetail(BaseModel):
    id: str
    title: str
    level: str
    time_estimate: str
    prerequisites: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)
    completed: bool
    description: str
    steps: list[str] = Field(default_factory=list)


# -- /api/doctor -----------------------------------------------------------


class DoctorCheck(BaseModel):
    name: str
    status: str  # "pass" | "warn" | "fail"
    message: str


class DoctorResponse(BaseModel):
    overall: str  # "healthy" | "warning" | "error"
    checks: list[DoctorCheck]


# -- /api/artifacts --------------------------------------------------------


class ReportSummary(BaseModel):
    title: str
    generated: str
    content: str


class ReportDetail(BaseModel):
    module_id: str
    content: str


# -- /api/run --------------------------------------------------------------


class RunStartResponse(BaseModel):
    run_id: str
    status: str


class RunStreamMessage(BaseModel):
    """WebSocket message envelope."""

    type: str  # "step" | "output" | "step_complete" | "tx" | "error" | "complete"
    # Remaining fields vary by type -- this is the base envelope

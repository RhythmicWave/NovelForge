from typing import Optional, Any, List
from pydantic import BaseModel


class WorkflowBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: Optional[bool] = True
    is_built_in: Optional[bool] = False
    version: Optional[int] = 1
    dsl_version: Optional[int] = 1
    definition_json: Optional[dict] = None


class WorkflowCreate(WorkflowBase):
    pass


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    version: Optional[int] = None
    dsl_version: Optional[int] = None
    definition_json: Optional[dict] = None


class WorkflowRead(WorkflowBase):
    id: int

    class Config:
        from_attributes = True


class WorkflowRunRead(BaseModel):
    id: int
    workflow_id: int
    definition_version: int
    status: str
    scope_json: Optional[dict] = None
    params_json: Optional[dict] = None
    idempotency_key: Optional[str] = None
    summary_json: Optional[dict] = None
    error_json: Optional[dict] = None

    class Config:
        from_attributes = True


class RunRequest(BaseModel):
    scope_json: Optional[dict] = None
    params_json: Optional[dict] = None
    idempotency_key: Optional[str] = None


class CancelResponse(BaseModel):
    ok: bool
    message: Optional[str] = None




# ---- Triggers ----

class WorkflowTriggerBase(BaseModel):
    workflow_id: int
    trigger_on: str  # onsave | ongenfinish | manual
    card_type_name: Optional[str] = None
    filter_json: Optional[dict] = None
    is_active: Optional[bool] = True


class WorkflowTriggerCreate(WorkflowTriggerBase):
    pass


class WorkflowTriggerUpdate(BaseModel):
    trigger_on: Optional[str] = None
    card_type_name: Optional[str] = None
    filter_json: Optional[dict] = None
    is_active: Optional[bool] = None


class WorkflowTriggerRead(WorkflowTriggerBase):
    id: int

    class Config:
        from_attributes = True

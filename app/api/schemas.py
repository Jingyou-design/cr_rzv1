"""Pydantic Schema 定义（工作流模型 + API 响应模型）"""

import operator
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field


# ── 工作流 Schema ────────────────────────────────────────────────
class CodeFile(BaseModel):
    filename: str = Field(description="文件名，含.py后缀")
    content: str = Field(description="文件完整源码")

class CodeGenResult(BaseModel):
    files: list[CodeFile] = Field(description="生成的多个代码文件")

class ModulePlan(BaseModel):
    name: str = Field(description="模块文件名（不含.py，下划线命名）；第一个必须为 shared_core")
    description: str = Field(description="模块职责和核心功能描述")
    key_classes: list[str] = Field(default_factory=list, description="关键类名")
    key_functions: list[str] = Field(default_factory=list, description="关键函数名")
    dependencies: list[str] = Field(default_factory=list, description="依赖的本项目模块名，不含 .py")


class PlanResult(BaseModel):
    modules: list[ModulePlan] = Field(description="6-8个模块：shared_core 加 5-7 个业务模块")


class CodeGenState(BaseModel):
    spec_text: str = ""
    output_dir: str = ""
    modules: list[dict] = Field(default_factory=list)
    current_idx: int = 0
    generated_code: dict[str, str] = Field(default_factory=dict)
    file_list: Annotated[list[str], operator.add] = Field(default_factory=list)

class GenerateRequest(BaseModel):
    file_url: str = Field(..., description="上传文件 URL")
# ── API 响应 Schema ──────────────────────────────────────────────

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class GenerateResponseAgent(BaseModel):
    file_url: str = Field(..., description="输出文件 URL")

class GenerateResponse(BaseModel):
    task_ids: list[str]
    task_id: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    stage: str | None = None
    error: str | None = None

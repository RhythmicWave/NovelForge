from __future__ import annotations

from typing import Any, Optional, Protocol

from loguru import logger
from pydantic import BaseModel
from sqlmodel import Session

from app.schemas.memory import ParticipantTyped


def log_extract_prompt(
    tag: str,
    prompt_name: Optional[str],
    llm_config_id: int,
    system_prompt: str,
    user_prompt: str,
) -> None:
    logger.info(
        f"[MemoryExtractPrompt][{tag}] prompt_name={prompt_name!r} llm_config_id={llm_config_id}\n"
        f"[system_prompt]\n{system_prompt}\n"
        f"[user_prompt]\n{user_prompt}"
    )

class BaseMemoryExtractor(Protocol):
    code: str
    name: str
    target: str
    preview_supported: bool
    output_model: type[BaseModel]

    async def extract(
        self,
        *,
        service: Any,
        session: Session,
        project_id: int | None,
        text: str,
        participants: list[ParticipantTyped],
        llm_config_id: int,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
        extra_context: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> BaseModel: ...

    def persist(
        self,
        *,
        service: Any,
        session: Session,
        project_id: int,
        data: BaseModel,
        options: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def build_affected_targets(self, data: BaseModel) -> list[dict[str, Any]]: ...

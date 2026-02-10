from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class BookStageItem(BaseModel):
    """拆书阶段条目（用于阶段划分/合并）"""

    stage_name: str = Field(description="阶段名称，例如：穿越与萌芽")
    chapter_start: int = Field(description="阶段起始章节号（全书序号，从1开始）", ge=1)
    chapter_end: int = Field(description="阶段结束章节号（全书序号，从1开始）", ge=1)
    stage_outline: str = Field(
        description=(
            "阶段故事大纲（Markdown 文本），必须包含：阶段起因、阶段目标、冲突与阻力、"
            "关键事件链（至少3条）、角色关系/能力变化、阶段结果与下一阶段钩子；"
            "要求细致、可执行，重点体现主角与主要角色变化。"
        )
    )

    stage_summary: Optional[str] = Field(
        default=None,
        description="阶段剧情概述（400~800字），用流畅叙事概述该阶段的剧情推进",
    )


class BookStageChunkPlan(BaseModel):
    """单个章节上下文块的阶段划分结果"""

    stages: List[BookStageItem] = Field(
        default_factory=list,
        description="当前上下文块内建议的阶段列表（可1~N个）"
    )


class BookStageFinalPlan(BaseModel):
    """全书最终阶段规划结果"""

    stages: List[BookStageItem] = Field(
        default_factory=list,
        description="全书最终阶段划分（需满足最大阶段数约束）"
    )

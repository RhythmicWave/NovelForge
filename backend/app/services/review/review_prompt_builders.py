from typing import Any

from app.schemas.chapter_review import ReviewRunRequest


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "\n".join(_to_text(item) for item in value if _to_text(item))
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            rendered = _to_text(item)
            if rendered:
                lines.append(f"{key}: {rendered}")
        return "\n".join(lines)
    return str(value)


def build_review_prompt(request: ReviewRunRequest) -> str:
    parts: list[str] = [
        "【审核目标】",
        f"标题：{request.title}",
        f"审核类型：{request.review_type}",
        f"审核 profile：{request.review_profile}",
        f"目标字段：{request.target_field}",
    ]

    if request.context_info:
        parts.extend(["", "【引用上下文】", request.context_info.strip()])
    if request.facts_info:
        parts.extend(["", "【事实子图】", request.facts_info.strip()])

    target_text = _to_text(request.target_text)
    parts.extend(["", "【待审核内容】", target_text or "（空内容）"])
    return "\n".join(parts)

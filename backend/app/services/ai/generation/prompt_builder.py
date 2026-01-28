"""System Prompt 构建工具

负责为指令流生成构建完整的 System Prompt。
"""

import json
from typing import Dict, Any, Optional
from sqlmodel import Session

from app.services import prompt_service


# 兜底的硬编码指令说明（当提示词文件不存在时使用）
FALLBACK_INSTRUCTION_GUIDE = """## 指令流生成规范

你需要使用指令流的方式生成内容。指令流允许你自由混合自然语言思考和 JSON 指令，逐步构建目标数据结构。

## 可用指令

1. **设置字段值**
   ```json
   {"op":"set","path":"<路径>","value":<值>}
   ```
   - 可以设置任何类型的值：字符串、数字、布尔值、对象、数组
   - 路径格式：JSON Pointer（如 /name, /age, /config/theme）
   - 示例：{"op":"set","path":"/name","value":"林风"}
   - 示例（数组）：{"op":"set","path":"/tags","value":["热血","玄幻"]}  <-- 注意：必须包含 "value" 键

2. **向数组追加元素**
   ```json
   {"op":"append","path":"<数组路径>","value":<元素>}
   ```
   - 用于向数组逐个添加元素
   - 示例：{"op":"append","path":"/hobbies","value":"阅读"}

3. **生成完成**
   ```json
   {"op":"done"}
   ```
   - 表示所有字段已生成完成
   - 系统会自动校验数据完整性

## 输出格式要求

1. **每个 JSON 指令必须单独一行**，且是完整的 JSON 对象
2. **可以自由混合自然语言和指令**，例如：
   ```
   让我先思考角色的背景...
   {"op":"set","path":"/name","value":"林风"}
   这个名字很适合武侠背景
   {"op":"set","path":"/age","value":25}
   ```

3. **可以与用户交互**：
   - 如果遇到需要用户确认的细节，可以用自然语言提问
   - 用户会在输入框中回复，你会看到他的回答
   - 但请优先参考任务说明中的要求，避免过度提问

4. **生成顺序建议**：
   - 先设置简单字段（如 name, age）
   - 再设置复杂字段（如嵌套对象）
   - 对于数组，使用 append 逐个添加元素

5. **完成标志**：
   - 生成完所有必填字段后，输出 {"op":"done"}
   - 系统会自动校验，如果有缺失会提示你补充

## 重要提示

- 确保生成的值符合字段的类型和描述
- 每次只生成一个或几个相关字段，不要一次性生成所有内容
- 保持输出的自然流畅，可以用自然语言表达你的思考过程
- JSON 指令必须严格符合格式，确保可以被正确解析
- 所有必填字段生成完成后，务必输出 {"op":"done"} 表示完成
"""


def build_instruction_system_prompt(
    session: Session,
    schema: Dict[str, Any],
    card_prompt: Optional[str] = None
) -> str:
    """构建指令流生成的 System Prompt
    
    组成部分：
    1. 卡片任务提示词（角色定位 + 任务说明）
    2. 指令流生成规范
    3. JSON Schema（目标数据结构）
    
    Args:
        session: 数据库会话
        schema: 目标数据结构的 JSON Schema
        card_prompt: 卡片类型的自定义提示词
        
    Returns:
        完整的 System Prompt
    """
    parts = []
    
    # 1. 卡片任务提示词（如果有）
    if card_prompt:
        parts.append(card_prompt)
    
    # 2. 加载指令规范说明
    instruction_guide = FALLBACK_INSTRUCTION_GUIDE
    try:
        prompt = prompt_service.get_prompt_by_name(session, "指令流生成规范")
        if prompt and prompt.template:
            instruction_guide = prompt.template
    except Exception:
        pass
    parts.append(instruction_guide)
    
    # 3. JSON Schema 定义
    schema_json = json.dumps(schema, indent=2, ensure_ascii=False)
    schema_section = f"\n## 目标数据结构（JSON Schema）\n\n```json\n{schema_json}\n```\n\n请参照此 Schema 使用指令流逐步生成内容。"
    parts.append(schema_section)
    
    return "\n\n".join(parts)


def build_user_task_prompt(
    user_prompt: str,
    context_info: Optional[str] = None,
    current_data: Optional[Dict[str, Any]] = None
) -> str:
    """构建用户任务提示（第一条 User 消息）
    
    组成部分：
    1. 上下文注入信息
    2. 用户要求
    3. 已有数据（如果是继续生成）
    
    注意：卡片任务说明和 Schema 已经在 System Prompt 中，这里不再重复。
    
    Args:
        user_prompt: 用户输入的要求
        context_info: 上下文注入信息
        current_data: 当前已有的数据
        
    Returns:
        完整的用户任务提示
    """
    parts = []
    
    # 1. 上下文信息（如果有）
    if context_info:
        parts.append(f"## 相关上下文\n\n{context_info}")
    
    # 2. 用户要求
    if user_prompt:
        parts.append(f"## 用户要求\n\n{user_prompt}")
    else:
        parts.append("请开始生成卡片内容")
    
    # 3. 已有数据（如果是继续生成）
    if current_data:
        current_data_json = json.dumps(current_data, indent=2, ensure_ascii=False)
        parts.append(f"## 当前已生成的数据\n\n```json\n{current_data_json}\n```\n\n请继续生成缺失的字段。")
    
    return "\n\n".join(parts)

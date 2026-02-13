"""
灵感助手工具函数集合（LangChain 原生工具实现）。
"""
import json
import uuid
from typing import Dict, Any, List, Optional
from contextvars import ContextVar

from loguru import logger
from langchain_core.tools import tool

from app.services.card_service import CardService
from app.db.models import Card, CardType
from app.services.ai.generation.instruction_validator import InstructionExecutor
from app.services.ai.card_type_schema import get_card_type_schema_payload
from app.schemas.tool_result import (
    ToolResult,
    ToolResultStatus,
    ConfirmationRequest,
    CardOperationResult,
    to_dict
)
import copy


class AssistantDeps:
    """灵感助手的依赖（用于传递 session 和 project_id）。"""

    def __init__(self, session, project_id: int):
        self.session = session
        self.project_id = project_id


# 使用 ContextVar 在每个请求上下文中注入依赖，避免为每个工具再包一层。
_assistant_deps_var: ContextVar[AssistantDeps | None] = ContextVar(
    "assistant_deps", default=None
)


def set_assistant_deps(deps: AssistantDeps) -> None:
    """为当前请求上下文设置助手依赖，在调用工具前必须先设置。"""

    _assistant_deps_var.set(deps)


def _get_deps() -> AssistantDeps:
    """获取当前请求上下文中的助手依赖。"""

    deps = _assistant_deps_var.get()
    if deps is None:
        raise RuntimeError(
            "AssistantDeps 未设置，请在调用助手工具前先调用 set_assistant_deps(...)。"
        )
    return deps


def _get_card_type_schema(session, card_type_name: str) -> Dict[str, Any]:
    """获取卡片类型的 JSON Schema"""
    result = get_card_type_schema_payload(
        session,
        card_type_name,
        allow_model_name=False,
        require_schema=True,
    )
    if not result.get("success"):
        error = result.get("error")
        if error == "not_found":
            raise ValueError(f"卡片类型 '{card_type_name}' 不存在")
        if error == "schema_not_defined":
            raise ValueError(f"卡片类型 '{card_type_name}' 没有定义 Schema")
        raise ValueError("获取卡片类型 Schema 失败")
    return result.get("schema") or {}


def _create_empty_card(session, card_type_name: str, title: str, parent_card_id: Optional[int], project_id: int) -> Card:
    """创建空卡片"""
    card_type = session.query(CardType).filter_by(name=card_type_name).first()
    if not card_type:
        raise ValueError(f"卡片类型 '{card_type_name}' 不存在")
    
    card = Card(
        card_type_id=card_type.id,
        project_id=project_id,
        title=title,
        parent_id=parent_card_id,
        content={}
    )
    session.add(card)
    session.flush()  # 获取 card.id
    
    return card


def _get_card_by_id(session, card_id: int, project_id: int) -> Optional[Card]:
    """根据ID获取卡片"""
    card = session.get(Card, card_id)
    if card and card.project_id == project_id:
        return card
    return None


@tool
def search_cards(
    card_type: Optional[str] = None,
    title_keyword: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    搜索项目中的卡片
    
    Args:
        card_type: 卡片类型名称（可选）
        title_keyword: 标题关键词（可选）
        limit: 返回结果数量上限
    
    Returns:
        success: True 表示成功，False 表示失败
        error: 错误信息
        cards: 卡片列表
        count: 卡片数量
    """

    deps = _get_deps()

    logger.info(f" [Assistant.search_cards] card_type={card_type}, keyword={title_keyword}")

    query = deps.session.query(Card).filter(Card.project_id == deps.project_id)
    
    if card_type:
        query = query.join(CardType).filter(CardType.name == card_type)
    
    if title_keyword:
        query = query.filter(Card.title.ilike(f'%{title_keyword}%'))
    
    cards = query.limit(limit).all()
    
    result = {
        "success": True,
        "cards": [
            {
                "id": c.id,
                "title": c.title,
                "type": c.card_type.name if c.card_type else "Unknown"
            }
            for c in cards
        ],
        "count": len(cards)
    }
    
    logger.info(f"✅ [Assistant.search_cards] 找到 {len(cards)} 个卡片")
    return result


@tool
def create_card(
    card_type: str,
    title: str,
    instructions: List[Dict[str, Any]],
    parent_card_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    创建**新**卡片并填充内容。
    
    ⚠️ **核心规则**：
    - ✅ **创建新卡片**：仅当用户明确要求新建时使用。
    - ❌ **修改/完善**：若需修改现有卡片或补充内容，必须使用 `update_card`。
    - ✅ **显式赋值**：即使字段有默认值，也必须显式生成指令进行赋值，以确认 AI 的意图。
    
    **策略建议（分步创建）**：
    - **复杂卡片**：推荐先仅填充核心字段（如 name）创建框架，获取 ID 后再通过 `update_card` 分批补充剩余内容。这能降低错误率并允许中途调整。
    - **简单卡片**：可一次性创建。
    
    Args:
        card_type: 卡片类型（如：角色卡、世界观设定）
        title: 标题
        instructions: 指令数组，如 `[{"op":"set", "path":"/name", "value":"张三"}]`
        parent_card_id: (可选) 父卡片ID
    
    Returns:
        包含 success, card_id, missing_fields 等信息。
        若 success=False (内容不完整)，请根据 missing_fields 生成补充指令并调用 update_card。
    """
    deps = _get_deps()
    
    logger.info(f"📝 [Assistant.create_card] type={card_type}, title={title}, instructions={len(instructions)}")
    
    try:
        # 1. 获取Schema
        schema = _get_card_type_schema(deps.session, card_type)
        
        # 2. 创建空卡片
        card = _create_empty_card(
            session=deps.session,
            card_type_name=card_type,
            title=title,
            parent_card_id=parent_card_id,
            project_id=deps.project_id
        )
        
        logger.info(f"  创建空卡片成功, card_id={card.id}")
        
        # 3. 创建指令执行器
        executor = InstructionExecutor(schema=schema, initial_data={})
        
        # 4. 执行指令数组
        result = executor.execute_batch(instructions)
        
        # 5. 保存数据并标记为 AI 修改
        card.content = result["data"]
        card.ai_modified = True
        card.needs_confirmation = True
        card.last_modified_by = "ai"
        deps.session.commit()
        
        logger.info(f"  指令执行完成: applied={result['applied']}, failed={result['failed']}")
        logger.info(f"  已标记为 AI 修改，需要用户确认")
        
        # 6. 构建返回结果
        if result["success"]:
            logger.info(f"✅ [Assistant.create_card] 创建成功且内容完整")
            return {
                "success": True,
                "card_id": card.id,
                "card_title": title,
                "card_type": card_type,
                "message": f"✅ 卡片《{title}》创建成功，填充了 {result['applied']} 个字段。请在前端检查内容后点击保存以触发工作流。",
                "applied": result['applied'],
                "needs_confirmation": True
            }
        else:
            # 数据不完整
            missing_fields_str = ", ".join(result["missing_fields"])
            logger.warning(f"⚠️ [Assistant.create_card] 卡片已创建但内容不完整: {missing_fields_str}")
            return {
                "success": False,
                "card_id": card.id,
                "card_title": title,
                "card_type": card_type,
                "message": f"⚠️ 卡片已创建但内容不完整，需要补充字段。补充完成后请在前端点击保存以触发工作流。",
                "error": f"缺失必填字段：{missing_fields_str}",
                "missing_fields": result["missing_fields"],
                "current_data": result["data"],
                "applied": result["applied"],
                "failed": result["failed"],
                "failed_instructions": result.get("errors", []),
                "needs_confirmation": True
            }
    
    except Exception as e:
        logger.error(f"❌ [Assistant.create_card] 失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"创建失败: {str(e)}"
        }


def _update_card_impl(
    card_id: int,
    instructions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    更新卡片的内部实现（核心逻辑）
    
    此函数包含实际的更新逻辑，可被多个工具函数复用。
    不要直接暴露给 LLM，而是通过 @tool 装饰的函数调用。
    """
    deps = _get_deps()
    
    logger.info(f"📝 [_update_card_impl] card_id={card_id}, instructions={len(instructions)}")
    
    try:
        # 1. 获取卡片
        card = _get_card_by_id(deps.session, card_id, deps.project_id)
        if not card:
            return {
                "success": False,
                "error": f"卡片 ID={card_id} 不存在或不属于当前项目"
            }
        
        # 2. 获取Schema
        schema = _get_card_type_schema(deps.session, card.card_type.name)
        
        # 3. 创建执行器（使用现有数据）
        executor = InstructionExecutor(
            schema=schema,
            initial_data=card.content or {}
        )
        
        # 4. 执行指令
        result = executor.execute_batch(instructions)
        
        # 5. 保存并标记为 AI 修改
        card.content = result["data"]
        card.ai_modified = True
        card.needs_confirmation = True
        card.last_modified_by = "ai"
        deps.session.commit()
        
        logger.info(f"  指令执行完成: applied={result['applied']}, failed={result['failed']}")
        logger.info(f"  已标记为 AI 修改，需要用户确认")
        
        # 6. 返回结果
        if result["success"]:
            logger.info(f"✅ [_update_card_impl] 更新成功且内容完整")
            return {
                "success": True,
                "card_id": card_id,
                "card_title": card.title,
                "message": f"✅ 卡片《{card.title}》更新成功，修改了 {result['applied']} 个字段。请在前端检查内容后点击保存以触发工作流。",
                "current_data": result["data"],
                "applied": result["applied"],
                "needs_confirmation": True
            }
        else:
            missing_fields_str = ", ".join(result["missing_fields"])
            logger.warning(f"⚠️ [_update_card_impl] 卡片已更新但仍不完整: {missing_fields_str}")
            return {
                "success": False,
                "card_id": card_id,
                "card_title": card.title,
                "message": f"⚠️ 卡片已更新但仍不完整，需要继续补充字段。补充完成后请在前端点击保存以触发工作流。",
                "error": f"缺失必填字段：{missing_fields_str}",
                "missing_fields": result["missing_fields"],
                "current_data": result["data"],
                "applied": result["applied"],
                "failed": result["failed"],
                "needs_confirmation": True
            }
    
    except Exception as e:
        logger.error(f"❌ [_update_card_impl] 失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"更新失败: {str(e)}"
        }


@tool
def update_card(
    card_id: int,
    instructions: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    更新**现有**卡片内容（执行指令数组）
    
    ⚠️ **重要：何时使用此工具？**
    
    - ✅ **修改现有卡片**：用户选中/引用了某个卡片，要求修改或完善
    - ✅ **补充内容**：用户说"完善这个卡片"、"补充内容"、"添加字段"等
    - ✅ **分步创建**：使用 create_card 创建基础框架后，逐步补充内容
    - ❌ **创建新卡片**：如果是创建全新的卡片，应该使用 create_card
    
    **判断依据：**
    1. 如果对话上下文中有卡片引用（如 @卡片名称），使用此工具
    2. 如果用户说"修改"、"完善"、"补充"、"更新"，使用此工具
    3. 如果是 create_card 返回不完整，继续补充内容，使用此工具
    
    用于补充或修改已存在卡片的内容。支持批量修改多个字段。
    
    Args:
        card_id: 卡片ID
        instructions: 指令数组，每个指令包含：
            - op: 操作类型（"set" 设置字段，"append" 追加到数组）
            - path: 字段路径（JSON Pointer 格式，如 "/name"）
            - value: 要设置的值
    
    Returns:
        Dict 包含:
        - success (bool): 是否成功
        - message (str): 结果消息
        - card_id (int): 卡片ID
        - card_title (str): 卡片标题
        - current_data (dict): 更新后的完整数据
        - applied (int): 成功执行的指令数
        - missing_fields (list, 可选): 仍缺失的必填字段路径列表
        - failed (int, 可选): 失败的指令数
    
    Examples:
        # 补充缺失字段
        update_card(
            card_id=123,
            instructions=[
                {"op":"set", "path":"/personality", "value":"正直勇敢"},
                {"op":"set", "path":"/background", "value":"武当弟子"},
                {"op":"append", "path":"/skills", "value":"降龙十八掌"}
            ]
        )
    """
    return _update_card_impl(card_id, instructions)


@tool
def modify_card_field(
    card_id: int,
    field_path: str,
    new_value: Any,
) -> Dict[str, Any]:
    """
    快速修改单个字段（便捷工具）
    
    这是 update_card 的简化版本，用于快速修改单个字段。
    如需同时修改多个字段，请使用 update_card 工具。
    
    Args:
        card_id: 卡片ID
        field_path: 字段路径，不需要前导斜杠（如 "name" 或 "personality"）
        new_value: 新值（字符串、数字、布尔值等）
    
    Returns:
        Dict 包含:
        - success (bool): 是否成功
        - message (str): 结果消息
        - card_id (int): 卡片ID
        - card_title (str): 卡片标题
    
    Examples:
        # 修改角色名称
        modify_card_field(card_id=123, field_path="name", new_value="李四")
        
        # 修改角色性格
        modify_card_field(card_id=123, field_path="personality", new_value="正直勇敢")
    """
    # 转换为指令格式（添加前导斜杠）
    path = "/" + field_path if not field_path.startswith("/") else field_path
    instruction = {"op": "set", "path": path, "value": new_value}
    
    # 调用内部实现（不是调用 @tool 装饰的函数）
    return _update_card_impl(card_id=card_id, instructions=[instruction])


@tool
def get_card_type_schema(
    card_type_name: str,
) -> Dict[str, Any]:
    """
    获取指定卡片类型的 JSON Schema 定义
    
    使用场景：当需要创建卡片但不清楚其结构时调用
    
    Args:
        card_type_name: 卡片类型名称
    
    Returns:
        success: True 表示成功，False 表示失败
        error: 错误信息
        card_type: 卡片类型名称
        schema: 卡片类型的 JSON Schema 定义
        description: 卡片类型的描述
    """

    deps = _get_deps()

    logger.info(f" [Assistant.get_card_type_schema] card_type={card_type_name}")

    result = get_card_type_schema_payload(
        deps.session,
        card_type_name,
        allow_model_name=False,
        require_schema=False,
    )

    if not result.get("success"):
        logger.warning(
            f"⚠️ [Assistant.get_card_type_schema] 卡片类型 '{card_type_name}' 不存在"
        )
        return {
            "success": False,
            "error": f"卡片类型 '{card_type_name}' 不存在"
        }

    output = {
        "success": True,
        "card_type": result.get("card_type") or card_type_name,
        "schema": result.get("schema") or {},
        "description": f"卡片类型 '{card_type_name}' 的完整结构定义"
    }

    logger.info(f"✅ [Assistant.get_card_type_schema] 已返回 Schema：{output}")
    return output


@tool
def get_card_content(
    card_id: int,
) -> Dict[str, Any]:
    """
    获取指定卡片的详细内容
    
    使用场景：需要查看卡片的完整数据时调用
    
    Args:
        card_id: 卡片ID
    
    Returns:
        success: True 表示成功，False 表示失败
        error: 错误信息（失败时）
        card_id: 卡片ID
        title: 卡片标题
        card_type: 卡片类型
        parent_id: 父卡片ID（None表示根级卡片）
        parent_title: 父卡片标题（如果有父卡片）
        parent_type: 父卡片类型（如果有父卡片）
        content: 卡片内容
        created_at: 卡片创建时间
    """

    deps = _get_deps()

    logger.info(f" [Assistant.get_card_content] card_id={card_id}")

    card = deps.session.query(Card).filter(Card.id == card_id).first()
    
    if not card:
        logger.warning(f"⚠️ [Assistant.get_card_content] 卡片 #{card_id} 不存在")
        return {
            "success": False,
            "error": f"卡片 #{card_id} 不存在"
        }
    
    result = {
        "success": True,
        "card_id": card.id,
        "title": card.title,
        "card_type": card.card_type.name if card.card_type else "Unknown",
        "parent_id": card.parent_id,  # 父卡片ID，用于了解层级关系
        "content": card.content or {},
        "created_at": str(card.created_at) if card.created_at else None
    }
    
    # 如果有父卡片，添加父卡片信息
    if card.parent_id and card.parent:
        result["parent_title"] = card.parent.title
        result["parent_type"] = card.parent.card_type.name if card.parent.card_type else "Unknown"
    
    logger.info(
        f"✅ [Assistant.get_card_content] 已返回卡片内容 (parent_id={card.parent_id})"
    )
    return result


@tool
def replace_field_text(
    card_id: int,
    field_path: str,
    old_text: str,
    new_text: str,
) -> Dict[str, Any]:
    """
    替换卡片字段中的指定文本片段
    
    使用场景：当用户对长文本字段的某部分内容不满意，希望只替换该部分时调用
    适用于章节正文、大纲描述等长文本字段的局部修改
    
    Examples:
        1. 精确匹配（短文本）：
        replace_field_text(card_id=42, field_path="content", 
                            old_text="林风犹豫了片刻", 
                            new_text="林风毫不犹豫地")
        
        2. 模糊匹配（长文本）：
        replace_field_text(card_id=42, field_path="content",
                            old_text="少年面色苍白，额头青筋暴起...现在却成了个废人。",
                            new_text="新的完整段落内容...")
    
    Args:
        card_id: 目标卡片的ID
        field_path: 字段路径（如 "content" 表示章节正文，"overview" 表示概述）
        old_text: 要被替换的原文片段，支持两种模式：
            1. 精确匹配：提供完整的原文（适用于短文本，50字以内）
            2. 模糊匹配：提供开头10字 + "..." + 结尾10字（适用于长文本，50字以上）
        new_text: 新的文本内容
    
    
    
    Returns:
        success: True 表示成功，False 表示失败
        error: 错误信息
        card_title: 卡片标题
        replaced_count: 替换的次数
        message: 用户友好的消息
    """

    logger.info(f" [Assistant.replace_field_text] card_id={card_id}, path={field_path}")
    logger.info(f"  要替换的文本长度: {len(old_text)} 字符")
    logger.info(f"  新文本长度: {len(new_text)} 字符")

    try:
        # Use CardService logic directly
        service = CardService(deps.session)
        result = service.replace_field_text(
            card_id=card_id,
            field_path=field_path,
            old_text=old_text,
            new_text=new_text,
            fuzzy_match=True
        )

        # 如果Service执行失败
        if not result.get("success"):
            logger.warning(
                f"⚠️ [Assistant.replace_field_text] 替换失败: {result.get('error')}"
            )
            return result
        
        # Service already commits, but tool flow often expects us to handle it or just be sure.
        # CardService.replace_field_text does commit.
        
        logger.info(f"✅ [Assistant.replace_field_text] 替换成功")

        # 添加用户友好的消息
        result["message"] = (
            f"✅ 已在「{result.get('card_title')}」的 {field_path} 中替换 "
            f"{result.get('replaced_count')} 处内容"
        )

        return result

    except Exception as e:
        logger.error(f"❌ [Assistant.replace_field_text] 替换失败: {e}")
        return {"success": False, "error": f"替换失败: {str(e)}"}


@tool
def delete_card(
    card_id: int,
    skip_confirmation: bool = False
) -> Dict[str, Any]:
    """
    删除卡片（危险操作）
    
    ⚠️ **确认规则：**
    - **用户明确指令**（如"删除角色卡张三"）：可以直接执行，设置 skip_confirmation=True
    - **模糊指令或你自主判断**：必须先获取用户确认，设置 skip_confirmation=False
    
    **判断标准：**
    - 用户消息中明确指定了要删除的卡片（通过标题、ID等唯一标识） → 可直接执行
    - 用户说"删除那个卡片"、"删掉测试的"等模糊表述 → 需要确认
    - 你自己判断某个卡片需要删除（用户没有明说） → 需要确认
    
    **确认流程：**
    1. 首先以 skip_confirmation=False 调用，获取确认请求
    2. 工具返回 status="confirmation_required" 和卡片信息
    3. 向用户说明要删除的卡片详情，询问"是否确认删除？"
    4. 用户明确回复"确认"、"确认删除"后，以 skip_confirmation=True 再次调用
    
    Args:
        card_id: 要删除的卡片ID
        skip_confirmation: 是否跳过确认（默认 False，需要确认）
    
    Returns:
        Dict 包含:
        - 如果需要确认：{"status": "confirmation_required", "message": "...", "data": {...}}
        - 如果已确认：{"success": true, "message": "卡片已删除", ...}
    
    Examples:
        # 示例1：用户明确指令 "删除角色卡张三"
        delete_card(card_id=123, skip_confirmation=True)  # 直接执行
        
        # 示例2：用户模糊指令 "删除测试卡片" 或你自主判断需要删除
        # 第一步：获取确认
        result = delete_card(card_id=123, skip_confirmation=False)
        # 你："我需要删除卡片《测试》，此操作不可撤销。是否确认？"
        # 用户："确认删除"
        # 第二步：执行删除
        result = delete_card(card_id=123, skip_confirmation=True)
    """
    deps = _get_deps()
    
    logger.info(f"🗑️ [Assistant.delete_card] card_id={card_id}, skip_confirmation={skip_confirmation}")
    
    try:
        # 获取卡片信息
        card = _get_card_by_id(deps.session, card_id, deps.project_id)
        if not card:
            result = CardOperationResult(
                success=False,
                status=ToolResultStatus.FAILED,
                message=f"卡片 ID={card_id} 不存在或不属于当前项目",
                error=f"卡片 ID={card_id} 不存在"
            )
            return to_dict(result)
        
        # 检查是否有子卡片
        child_count = deps.session.query(Card).filter(
            Card.parent_id == card_id
        ).count()
        
        # 如果需要确认，返回确认请求
        if not skip_confirmation:
            warning = None
            if child_count > 0:
                warning = f"此卡片有 {child_count} 个子卡片，删除后子卡片也会被删除"
            
            result = ConfirmationRequest(
                confirmation_id=str(uuid.uuid4()),
                action="delete_card",
                action_params={"card_id": card_id},
                message=f"❓ 确认要删除卡片《{card.title}》吗？请用户明确说\"确认删除\"或\"取消\"",
                warning=warning,
                data={
                    "card_id": card_id,
                    "card_title": card.title,
                    "card_type": card.card_type.name,
                    "child_count": child_count
                }
            )
            logger.info(f"⚠️ [Assistant.delete_card] 等待用户确认")
            return to_dict(result)
        
        # 用户已确认，执行删除
        logger.info(f"✅ [Assistant.delete_card] 用户已确认，开始删除")
        
        # 删除子卡片（如果有）
        if child_count > 0:
            deps.session.query(Card).filter(Card.parent_id == card_id).delete()
            logger.info(f"  已删除 {child_count} 个子卡片")
        
        # 删除卡片本身
        card_title = card.title
        deps.session.delete(card)
        deps.session.commit()
        
        result = CardOperationResult(
            success=True,
            status=ToolResultStatus.SUCCESS,
            message=f"✅ 卡片《{card_title}》已成功删除" + (f"（包括 {child_count} 个子卡片）" if child_count > 0 else ""),
            card_id=card_id,
            card_title=card_title,
            data={"deleted_children": child_count}
        )
        logger.info(f"✅ [Assistant.delete_card] 删除成功")
        return to_dict(result)
    
    except Exception as e:
        logger.error(f"❌ [Assistant.delete_card] 失败: {e}", exc_info=True)
        result = CardOperationResult(
            success=False,
            status=ToolResultStatus.FAILED,
            message=f"删除失败: {str(e)}",
            error=str(e)
        )
        return to_dict(result)


@tool
def move_card(
    card_id: int,
    new_parent_id: Optional[int] = None,
    skip_confirmation: bool = False
) -> Dict[str, Any]:
    """
    移动卡片到新的父卡片下（危险操作）
    
    ⚠️ **确认规则：**
    - **用户明确指令**（如"把角色卡清风移动到核心蓝图下面"）：可以直接执行，设置 skip_confirmation=True
    - **模糊指令或你自主判断**：必须先获取用户确认，设置 skip_confirmation=False
    
    **判断标准：**
    - 用户明确说了要移动哪个卡片到哪里 → 可直接执行
    - 用户说"移动那个卡片"、"把它放到别处"等模糊表述 → 需要确认
    - 你自己判断某个卡片需要移动（用户没有明说） → 需要确认
    
    **确认流程：**
    1. 首先以 skip_confirmation=False 调用，获取确认请求
    2. 工具返回 status="confirmation_required" 和移动详情
    3. 向用户说明移动操作："将卡片《X》从 Y 移动到 Z，是否确认？"
    4. 用户明确回复"确认"、"确认移动"后，以 skip_confirmation=True 再次调用
    
    Args:
        card_id: 要移动的卡片ID
        new_parent_id: 新的父卡片ID（None 表示移动到根级别）
        skip_confirmation: 是否跳过确认（默认 False，需要确认）
    
    Returns:
        Dict 包含:
        - 如果需要确认：{"status": "confirmation_required", "message": "...", "data": {...}}
        - 如果已确认：{"success": true, "message": "卡片已移动", ...}
    
    Examples:
        # 示例1：用户明确指令 "把清风移动到核心蓝图下面"
        move_card(card_id=123, new_parent_id=456, skip_confirmation=True)  # 直接执行
        
        # 示例2：用户模糊指令或你自主判断
        # 第一步：获取确认
        result = move_card(card_id=123, new_parent_id=456, skip_confirmation=False)
        # 你："将卡片《清风》从根级别移动到《核心蓝图》下，是否确认？"
        # 用户："确认移动"
        # 第二步：执行移动
        result = move_card(card_id=123, new_parent_id=456, skip_confirmation=True)
    """
    deps = _get_deps()
    
    logger.info(f"📦 [Assistant.move_card] card_id={card_id}, new_parent={new_parent_id}, skip_confirmation={skip_confirmation}")
    
    try:
        # 1. 获取要移动的卡片
        card = _get_card_by_id(deps.session, card_id, deps.project_id)
        if not card:
            result = CardOperationResult(
                success=False,
                status=ToolResultStatus.FAILED,
                message=f"卡片 ID={card_id} 不存在或不属于当前项目",
                error=f"卡片 ID={card_id} 不存在"
            )
            return to_dict(result)
        
        # 2. 验证新父卡片
        new_parent = None
        if new_parent_id is not None:
            new_parent = _get_card_by_id(deps.session, new_parent_id, deps.project_id)
            if not new_parent:
                result = CardOperationResult(
                    success=False,
                    status=ToolResultStatus.FAILED,
                    message=f"目标父卡片 ID={new_parent_id} 不存在或不属于当前项目",
                    error=f"目标父卡片不存在"
                )
                return to_dict(result)
            
            # 防止循环引用：不能将卡片移动到自己或自己的子卡片下
            if new_parent_id == card_id:
                result = CardOperationResult(
                    success=False,
                    status=ToolResultStatus.FAILED,
                    message="不能将卡片移动到自己下面",
                    error="循环引用错误"
                )
                return to_dict(result)
            
            # TODO: 检查是否是子孙卡片（需要递归检查）
        
        # 3. 获取当前父卡片信息
        old_parent = None
        old_parent_title = "根级别"
        if card.parent_id:
            old_parent = deps.session.get(Card, card.parent_id)
            if old_parent:
                old_parent_title = f"《{old_parent.title}》"
        
        new_parent_title = "根级别" if not new_parent else f"《{new_parent.title}》"
        
        # 4. 如果需要确认，返回确认请求
        if not skip_confirmation:
            result = ConfirmationRequest(
                confirmation_id=str(uuid.uuid4()),
                action="move_card",
                action_params={
                    "card_id": card_id,
                    "new_parent_id": new_parent_id
                },
                message=f"❓ 确认要将卡片《{card.title}》从 {old_parent_title} 移动到 {new_parent_title} 吗？请用户明确说\"确认移动\"或\"取消\"",
                data={
                    "card_id": card_id,
                    "card_title": card.title,
                    "from_parent": old_parent_title,
                    "to_parent": new_parent_title
                }
            )
            logger.info(f"⚠️ [Assistant.move_card] 等待用户确认")
            return to_dict(result)
        
        # 5. 用户已确认，执行移动
        logger.info(f"✅ [Assistant.move_card] 用户已确认，开始移动")
        
        card.parent_id = new_parent_id
        deps.session.commit()
        
        result = CardOperationResult(
            success=True,
            status=ToolResultStatus.SUCCESS,
            message=f"✅ 卡片《{card.title}》已从 {old_parent_title} 移动到 {new_parent_title}",
            card_id=card_id,
            card_title=card.title,
            data={
                "from_parent": old_parent_title,
                "to_parent": new_parent_title
            }
        )
        logger.info(f"✅ [Assistant.move_card] 移动成功")
        return to_dict(result)
    
    except Exception as e:
        logger.error(f"❌ [Assistant.move_card] 失败: {e}", exc_info=True)
        result = CardOperationResult(
            success=False,
            status=ToolResultStatus.FAILED,
            message=f"移动失败: {str(e)}",
            error=str(e)
        )
        return to_dict(result)


# 导出所有 LangChain 工具（已通过 @tool 装饰）
ASSISTANT_TOOLS = [
    search_cards,
    create_card,
    update_card,
    modify_card_field,
    delete_card,
    move_card,
    replace_field_text,
    get_card_type_schema,
    get_card_content,
]

ASSISTANT_TOOL_REGISTRY = {tool.name: tool for tool in ASSISTANT_TOOLS}

ASSISTANT_TOOL_DESCRIPTIONS = {
    tool.name: {
        "description": tool.description,
        "args": tool.args,
    }
    for tool in ASSISTANT_TOOLS
}

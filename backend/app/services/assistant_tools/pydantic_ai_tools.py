"""
灵感助手工具函数集合
"""
from typing import Dict, Any, List, Optional
from pydantic_ai import RunContext
from loguru import logger
from app.services import nodes
from app.db.models import Card, CardType
import copy

class AssistantDeps:
    """灵感助手的依赖（用于传递 session 和 project_id）"""
    def __init__(self, session, project_id: int):
        self.session = session
        self.project_id = project_id


def search_cards(
    ctx: RunContext[AssistantDeps],
    card_type: Optional[str] = None,
    title_keyword: Optional[str] = None,
    limit: int = 10
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
    logger.info(f" [PydanticAI.search_cards] card_type={card_type}, keyword={title_keyword}")
    
    query = ctx.deps.session.query(Card).filter(Card.project_id == ctx.deps.project_id)
    
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
    
    logger.info(f"✅ [PydanticAI.search_cards] 找到 {len(cards)} 个卡片")
    return result


def create_card(
    ctx: RunContext[AssistantDeps],
    card_type: str,
    title: str,
    content: Dict[str, Any],
    parent_card_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    创建新卡片
    
    Examples:
        # 在项目根目录创建角色卡
        create_card(card_type="角色卡", title="张三", content={...})
        
        # 在某个分卷大纲（card_id=42）下创建章节大纲
        create_card(card_type="章节大纲", title="第一章", content={...}, parent_card_id=42)
    
    Args:
        card_type: 卡片类型名称（如：角色卡、章节大纲、世界观设定等）
        title: 卡片标题
        content: 卡片内容（字典，需符合该类型的 Schema）
        parent_card_id: 父卡片ID（可选）
            * 如果提供，则在指定卡片下创建子卡片
            * 如果不提供，则在项目根目录创建
    
    Returns:
        success: True 表示成功，False 表示失败
        error: 错误信息
        card_id: 卡片ID
        card_title: 卡片标题
        message: 用户友好的消息
    """
    
    logger.info(f" [PydanticAI.create_card] type={card_type}, title={title}, parent_id={parent_card_id}")
    
    state = {
        "scope": {
            "project_id": ctx.deps.project_id
        },
        "touched_card_ids": set()
    }
    
    # 构建 params，如果指定了父卡片ID，则添加到 parent 参数
    params = {
        "cardType": card_type,
        "title": title,
        "contentMerge": content
    }
    
    if parent_card_id is not None:
        params["parent"] = parent_card_id
        logger.info(f"  指定父卡片ID: {parent_card_id}")
    else:
        params["parent"] = "$projectRoot"
        logger.info(f"  在项目根目录创建")
    
    result = nodes.node_card_upsert_child_by_title(
        session=ctx.deps.session,
        state=state,
        params=params
    )
    
    # 提交事务（重要！）
    ctx.deps.session.commit()
    
    logger.info(f"✅ [PydanticAI.create_card] 创建成功: {result}")
    
    return {
        "success": True,
        "card_id": result.get("card_id"),
        "card_title": result.get("card_title", title),
        "message": f"✅ 已创建{card_type}「{title}」"
    }


def modify_card_field(
    ctx: RunContext[AssistantDeps],
    card_id: int,
    field_path: str,
    new_value: Any
) -> Dict[str, Any]:
    """
    修改指定卡片的字段内容
    
    使用场景：当用户要求将内容写入某卡片时，必须调用此工具执行
    
    Examples:
        - modify_card_field(card_id=27, field_path="overview", new_value="这是新的概述内容...")
        - modify_card_field(card_id=15, field_path="content.name", new_value="林风")
        - modify_card_field(card_id=8, field_path="chapter_outline_list", new_value=[...])
    
    Args:
        card_id: 目标卡片的ID（从项目结构树中查找）
        field_path: 字段路径，支持两种格式：
            * 简单字段："overview"、"stage_name" 等
            * 嵌套字段："content.overview"、"content.chapter_outline_list" 等
        new_value: 要设置的新值（可以是字符串、数字、列表、字典等）
    
    
    
    Returns:
        success: True 表示成功，False 表示失败
        error: 错误信息
        card_id: 卡片ID
        card_title: 卡片标题
        field_path: 字段路径
        new_value: 新的值
        message: 用户友好的消息
    """
    logger.info(f" [PydanticAI.modify_card_field] card_id={card_id}, path={field_path}")
    logger.info(f"  新值类型: {type(new_value)}")
    
    try:
        # 验证卡片存在性
        card = ctx.deps.session.get(Card, card_id)
        if not card or card.project_id != ctx.deps.project_id:
            logger.warning(f"⚠️ 卡片 {card_id} 不存在或不属于当前项目")
            return {
                "success": False,
                "error": f"卡片 {card_id} 不存在或不属于当前项目"
            }
        
        logger.info(f"  卡片标题: {card.title}")
        logger.info(f"  修改前: {card.content}")
        
        # 构造工作流节点所需的 state
        state = {
            "card": card,
            "touched_card_ids": set()
        }
        
        # 调用工作流节点函数
        nodes.node_card_modify_content(
            session=ctx.deps.session,
            state=state,
            params={
                "setPath": field_path,
                "setValue": new_value
            }
        )
        
        # 提交事务（重要！）
        ctx.deps.session.commit()
        
        # 刷新卡片数据
        ctx.deps.session.refresh(card)
        
        logger.info(f"  修改后: {card.content}")
        logger.info(f"✅ [PydanticAI.modify_card_field] 修改成功")
        
        return {
            "success": True,
            "card_id": card_id,
            "card_title": card.title,
            "field_path": field_path,
            "new_value": new_value,
            "message": f"✅ 已更新「{card.title}」的 {field_path.replace('content.', '')}"
        }
    
    except Exception as e:
        logger.error(f"❌ [PydanticAI.modify_card_field] 修改失败: {e}")
        return {
            "success": False,
            "error": f"修改失败: {str(e)}"
        }


def batch_create_cards(
    ctx: RunContext[AssistantDeps],
    card_type: str,
    cards: List[Dict[str, Any]],
    parent_card_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    批量创建同类型卡片
    
    Args:
        card_type: 卡片类型名称
        cards: 卡片数据列表，每项包含 title 和 content
        parent_card_id: 父卡片ID（可选）
    
    Returns:
        success: True 表示成功，False 表示失败
        error: 错误信息
        total: 卡片总数
        success_count: 成功创建的卡片数量
        failed_count: 失败创建的卡片数量
        results: 创建结果列表
    """
    logger.info(f" [PydanticAI.batch_create_cards] type={card_type}, count={len(cards)}")
    
    results = []
    
    for card_data in cards:
        try:
            title = card_data.get("title", "")
            content = card_data.get("content", {})
            
            result = create_card(ctx, card_type, title, content, parent_card_id)
            results.append({
                "title": title,
                "status": "success",
                "card_id": result["card_id"]
            })
        except Exception as e:
            logger.error(f"批量创建失败: {card_data.get('title', 'unknown')} - {e}")
            results.append({
                "title": card_data.get("title", "unknown"),
                "status": "failed",
                "error": str(e)
            })
    
    success_count = sum(1 for r in results if r["status"] == "success")
    
    logger.info(f"✅ [PydanticAI.batch_create_cards] 成功 {success_count}/{len(cards)}")
    
    return {
        "success": True,
        "total": len(cards),
        "success_count": success_count,
        "failed_count": len(cards) - success_count,
        "results": results
    }


def get_card_type_schema(
    ctx: RunContext[AssistantDeps],
    card_type_name: str
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
    logger.info(f" [PydanticAI.get_card_type_schema] card_type={card_type_name}")
    
    card_type = ctx.deps.session.query(CardType).filter(
        CardType.name == card_type_name
    ).first()
    
    if not card_type:
        logger.warning(f"⚠️ [PydanticAI.get_card_type_schema] 卡片类型 '{card_type_name}' 不存在")
        return {
            "success": False,
            "error": f"卡片类型 '{card_type_name}' 不存在"
        }
    
    result = {
        "success": True,
        "card_type": card_type_name,
        "schema": card_type.json_schema or {},
        "description": f"卡片类型 '{card_type_name}' 的完整结构定义"
    }
    
    logger.info(f"✅ [PydanticAI.get_card_type_schema] 已返回 Schema：{result}")
    return result


def get_card_content(
    ctx: RunContext[AssistantDeps],
    card_id: int
) -> Dict[str, Any]:
    """
    获取指定卡片的详细内容
    
    使用场景：需要查看卡片的完整数据时调用
    
    Args:
        card_id: 卡片ID
    
    Returns:
        success: True 表示成功，False 表示失败
        error: 错误信息
        card_id: 卡片ID
        title: 卡片标题
        card_type: 卡片类型
        content: 卡片内容
        created_at: 卡片创建时间
        message: 用户友好的消息
    """
    logger.info(f" [PydanticAI.get_card_content] card_id={card_id}")
    
    card = ctx.deps.session.query(Card).filter(Card.id == card_id).first()
    
    if not card:
        logger.warning(f"⚠️ [PydanticAI.get_card_content] 卡片 #{card_id} 不存在")
        return {
            "success": False,
            "error": f"卡片 #{card_id} 不存在"
        }
    
    result = {
        "success": True,
        "card_id": card.id,
        "title": card.title,
        "card_type": card.card_type.name if card.card_type else "Unknown",
        "content": card.content or {},
        "created_at": str(card.created_at) if card.created_at else None
    }
    
    logger.info(f"✅ [PydanticAI.get_card_content] 已返回卡片内容")
    return result


def replace_field_text(
    ctx: RunContext[AssistantDeps],
    card_id: int,
    field_path: str,
    old_text: str,
    new_text: str
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
    logger.info(f" [PydanticAI.replace_field_text] card_id={card_id}, path={field_path}")
    logger.info(f"  要替换的文本长度: {len(old_text)} 字符")
    logger.info(f"  新文本长度: {len(new_text)} 字符")
    
    try:
        # 验证卡片存在性和归属
        card = ctx.deps.session.get(Card, card_id)
        if not card or card.project_id != ctx.deps.project_id:
            logger.warning(f"⚠️ 卡片 {card_id} 不存在或不属于当前项目")
            return {
                "success": False,
                "error": f"卡片 {card_id} 不存在或不属于当前项目"
            }
        
        logger.info(f"  卡片标题: {card.title}")
        
        # 构造工作流节点所需的 state
        state = {
            "touched_card_ids": set()
        }
        
        # 调用工作流节点函数
        result = nodes.node_card_replace_field_text(
            session=ctx.deps.session,
            state=state,
            params={
                "card_id": card_id,
                "field_path": field_path,
                "old_text": old_text,
                "new_text": new_text
            }
        )
        
        # 如果节点执行失败，直接返回错误
        if not result.get("success"):
            logger.warning(f"⚠️ [PydanticAI.replace_field_text] 节点执行失败: {result.get('error')}")
            return result
        
        # 提交事务（重要！）
        ctx.deps.session.commit()
        
        logger.info(f"✅ [PydanticAI.replace_field_text] 替换成功")
        
        # 添加用户友好的消息
        result["message"] = f"✅ 已在「{result.get('card_title')}」的 {field_path.replace('content.', '')} 中替换 {result.get('replaced_count')} 处内容"
        
        return result
    
    except Exception as e:
        logger.error(f"❌ [PydanticAI.replace_field_text] 替换失败: {e}")
        return {
            "success": False,
            "error": f"替换失败: {str(e)}"
        }




# ✅ 导出所有工具函数列表（Pydantic AI 标准方式）
ASSISTANT_TOOLS = [
    search_cards,
    create_card,
    modify_card_field,
    replace_field_text,
    batch_create_cards,
    get_card_type_schema,
    get_card_content,
  
]



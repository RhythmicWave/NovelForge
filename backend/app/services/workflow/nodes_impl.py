"""工作流节点实现

所有工作流节点的具体实现。
"""

from __future__ import annotations

from typing import Any, Optional, List, Dict
import copy
from sqlmodel import Session, select
from pydantic import TypeAdapter, ValidationError
from loguru import logger

from app.db.models import Card, CardType
from .registry import register_node
from .utils import (
    parse_schema_fields,
    get_card_by_id,
    get_by_path,
    set_by_path,
    render_value,
    get_from_state,
)


@register_node("Card.Read")
def node_card_read(session: Session, state: dict, params: dict) -> dict:
    """
    Card.Read: 读取锚点卡片或指定 card_id，写入 state['card'] 并返回 {'card': Card}
    params:
      - target: "$self" | int(card_id)
      - type_name: 卡片类型名称，用于类型绑定和字段解析
    """
    target = params.get("target", "$self")
    type_name = params.get("type_name", "")
    
    card: Optional[Card] = None
    if target == "$self":
        scope = state.get("scope") or {}
        card_id = scope.get("card_id")
        if card_id:
            card = get_card_by_id(session, card_id)
    else:
        try:
            card = get_card_by_id(session, int(target))
        except Exception:
            card = None
    
    if not card:
        raise ValueError("Card.Read 未找到目标卡片")
    
    # 如果指定了类型名称，获取类型信息和字段结构
    card_type_info = None
    field_structure = None
    if type_name:
        from app.db.models import CardType
        card_type = session.exec(select(CardType).where(CardType.name == type_name)).first()
        if card_type and card_type.json_schema:
            card_type_info = {
                "id": card_type.id,
                "name": card_type.name,
                "schema": card_type.json_schema
            }
            # 解析字段结构
            field_structure = parse_schema_fields(card_type.json_schema)
    
    state["card"] = card
    state["current"] = {
        "card": card,
        "card_type_info": card_type_info,
        "field_structure": field_structure
    }
    
    # logger.info(f"[节点] 读取卡片 card_id={card.id} title={card.title} type={type_name}")
    return {
        "card": card,
        "card_type_info": card_type_info,
        "field_structure": field_structure
    }


@register_node("Card.ModifyContent")
def node_card_modify_content(session: Session, state: dict, params: dict) -> dict:
    """
    Card.ModifyContent: 将 params['contentMerge'](dict) 浅合并到当前 card.content
    兼容：setPath + setValue（直接设置路径值）
    params:
      - contentMerge: dict
      - setPath: string（可选，$.content.xxx 路径）
      - setValue: any（可选，支持表达式字符串）
    """
    card: Card = state.get("card")
    if not isinstance(card, Card):
        raise ValueError("Card.ModifyContent 缺少当前卡片，请先执行 Card.Read")

    # 优先处理 setPath/setValue
    set_path = params.get("setPath")
    if isinstance(set_path, str) and set_path:
        # 兼容 $card. 前缀（等价 $.）
        norm_path = set_path.strip()
        if norm_path.startswith("$card."):
            norm_path = "$." + norm_path[len("$card."):]
        
        # 如果路径不以 $. 开头，自动添加 $.content. 前缀
        if not norm_path.startswith("$."):
            norm_path = "$.content." + norm_path
        
        value_expr = params.get("setValue")
        value = get_from_state(value_expr, state)
        
        # 使用深拷贝避免修改原始对象
        base = copy.deepcopy(dict(card.content or {}))
        
        # 规范化路径：如果以 $.content. 开头，去掉该前缀
        if norm_path.startswith("$.content."):
            content_path = "$." + norm_path[len("$.content."):]
        else:
            content_path = norm_path
        
        # 设置值
        set_by_path(base, content_path, value)
        
        # 保存
        card.content = base
        session.add(card)
        session.commit()
        session.refresh(card)
        # logger.info(f"[节点] 按路径设置内容 card_id={card.id} path={set_path} value={value}")
        # 标记受影响卡片
        try:
            touched: set = state.setdefault("touched_card_ids", set())  # type: ignore[assignment]
            touched.add(int(card.id))
        except Exception:
            pass
        state["card"] = card
        state["current"] = {"card": card}
        return {"card": card}

    # 默认走合并
    content_merge = params.get("contentMerge") or {}
    content_merge = render_value(content_merge, state)
    if not isinstance(content_merge, dict):
        raise ValueError("contentMerge 需为对象")
    
    # 使用深拷贝避免修改原始对象
    base = copy.deepcopy(dict(card.content or {}))
    base.update(content_merge)
    card.content = base
    session.add(card)
    session.commit()
    session.refresh(card)
    # 标记受影响卡片
    try:
        touched2: set = state.setdefault("touched_card_ids", set())  # type: ignore[assignment]
        touched2.add(int(card.id))
    except Exception:
        pass
    state["card"] = card
    state["current"] = {"card": card}
    # logger.info(f"[节点] 修改卡片内容完成 card_id={card.id} 合并键={list(content_merge.keys())}")
    return {"card": card}


@register_node("Card.UpsertChildByTitle")
def node_card_upsert_child_by_title(session: Session, state: dict, params: dict) -> dict:
    """
    Card.UpsertChildByTitle: 在目标父卡片下按标题创建/更新子卡。
    params:
      - cardType: str (卡片类型名称)
      - title: str (可使用模板: {item.title} / {index} / { $.content.volume_number } 等)
      - titlePath: string（兼容：从路径/表达式获取标题）
      - parent: "$self" | "$projectRoot" | 具体 card_id（可选，默认 $self）
      - useItemAsContent: bool (true 则以 state['item'] 作为 content)
      - contentMerge: dict （与 useItemAsContent 二选一，合并到 content）
      - contentTemplate: dict|list|str （直接模板渲染为 content，优先于 contentMerge）
      - contentPath: string（兼容：从路径/表达式获取内容）
    依赖：state['card'] 为默认父卡；可选 state['item'] 供模板取值。
    """
    parent: Optional[Card] = state.get("card")
    # 允许未先读父卡；若未提供 parent，则在项目根创建

    card_type_name = params.get("cardType")
    if not card_type_name:
        raise ValueError("参数 cardType 必填")
    ct: Optional[CardType] = session.exec(select(CardType).where(CardType.name == card_type_name)).first()
    if not ct:
        raise ValueError(f"未找到卡片类型: {card_type_name}")

    try:
        adapter = TypeAdapter(Any, config={'json_schema': ct.json_schema})
        validated_data = adapter.validate_python(params.get("content"))

    except ValidationError as e:
        raise ValueError(f"卡片类型 {card_type_name} 的结构校验失败: {e.errors()}，请确保按照json schema格式生成内容")

    raw_title: Optional[str] = params.get("title")
    if not raw_title:
        title_path = params.get("titlePath")
        if isinstance(title_path, str) and title_path:
            resolved_title = get_from_state(title_path, state)
            if isinstance(resolved_title, (str, int, float)):
                raw_title = str(resolved_title)
    title = render_value(raw_title, state) if isinstance(raw_title, str) else raw_title
    if not isinstance(title, str) or not title.strip():
        title = ct.name or "未命名"

    # 解析 parent 目标
    parent_spec = params.get("parent") or ("$self" if isinstance(parent, Card) else "$projectRoot")
    target_parent_id: Optional[int]
    project_id: int
    if parent_spec in ("$self", None):
        if not isinstance(parent, Card):
            raise ValueError("需要先读取父卡片或提供 parent 目标")
        target_parent_id = parent.id
        project_id = parent.project_id
    elif parent_spec in ("$root", "$projectRoot", "$project_root"):
        if isinstance(parent, Card):
            project_id = parent.project_id
        else:
            scope = state.get("scope") or {}
            project_id = int(scope.get("project_id"))
        target_parent_id = None
    else:
        p = get_card_by_id(session, int(parent_spec))
        if not p:
            raise ValueError(f"未找到 parent 卡片: {parent_spec}")
        target_parent_id = p.id
        project_id = p.project_id

    # 查找同父、同类型、同标题是否已存在（避免不同类型同名卡片被误判为同一张）
    existing = session.exec(
        select(Card).where(
            Card.project_id == project_id,
            Card.parent_id == target_parent_id,
            Card.card_type_id == ct.id,
        )
    ).all()
    target = next((c for c in existing if str(c.title) == str(title)), None)

    use_item = bool(params.get("useItemAsContent"))
    # 若同时提供 useItemAsContent 与 contentMerge，则以 item 为基础再浅合并覆盖字段
    content_merge = params.get("contentMerge") if isinstance(params.get("contentMerge"), dict) else None
    content_template = params.get("contentTemplate") if isinstance(params.get("contentTemplate"), (dict, list, str)) else None
    content_path = params.get("contentPath") if isinstance(params.get("contentPath"), str) else None
    item = state.get("item") or {}

    if use_item:
        # 以当前 item 为基础，必要时再合并 contentMerge 进行字段覆盖
        content: Any = dict(item)
        if content_merge is not None:
            cm = render_value(content_merge or {}, state)
            if isinstance(cm, dict):
                content.update(cm)
    else:
        if content_template is not None:
            content = render_value(content_template, state)
            if not isinstance(content, dict):
                content = {"value": content}
        elif content_path:
            resolved = get_from_state(content_path, state)
            content = resolved if isinstance(resolved, dict) else {"value": resolved}
        else:
            base = dict(target.content) if target else {}
            cm = render_value(content_merge or {}, state)
            content = {**base, **(cm or {})}

    if target:
        target.content = content
        session.add(target)
        session.commit()
        session.refresh(target)
        result = target
        logger.info(f"[节点] 更新子卡 parent_id={target_parent_id} title={title} card_id={target.id}")
    else:
        new_card = Card(
            title=title,
            model_name=ct.model_name or ct.name,
            content=content,
            parent_id=target_parent_id,
            card_type_id=ct.id,
            json_schema=None,
            ai_params=None,
            project_id=project_id,
            display_order=len(existing),
            ai_context_template=ct.default_ai_context_template,
        )
        session.add(new_card)
        session.commit()
        session.refresh(new_card)
        result = new_card
        logger.info(f"[节点] 创建子卡 parent_id={target_parent_id} title={title} card_id={new_card.id}")

    state["last_child"] = result
    state["current"] = {"card": result}
    # 标记受影响卡片
    try:
        touched3: set = state.setdefault("touched_card_ids", set())  # type: ignore[assignment]
        touched3.add(int(getattr(result, "id", 0)))
        if isinstance(parent, Card) and parent.id:
            touched3.add(int(parent.id))
    except Exception:
        pass
    return {"card": result}


@register_node("List.ForEach")
def node_list_foreach(session: Session, state: dict, params: dict, run_body):
    """
    List.ForEach: 遍历列表并为每个元素执行 body 节点。
    params:
      - listPath: string 例如 "$.content.character_cards"
      - list: 任意（兼容：字符串路径或直接数组）
    """
    list_path = params.get("listPath")
    seq: Any = None
    if not isinstance(list_path, str) or not list_path:
        raw = params.get("list")
        # logger.info(f"[节点] List.ForEach 原始 list 参数 type={type(raw).__name__} value={raw!r}")
        if isinstance(raw, list):
            seq = raw
        elif isinstance(raw, dict):
            # 支持 { path: '$.content.xxx' }
            cand = raw.get("path") or raw.get("listPath")
            if isinstance(cand, str) and cand:
                seq = get_from_state(cand, state)
        elif isinstance(raw, str) and raw:
            seq = get_from_state(raw.strip(), state)
    if seq is None:
        if not isinstance(list_path, str) or not list_path:
            logger.warning("[节点] List.ForEach 缺少 listPath")
            return
        card = state.get("card") or (state.get("current") or {}).get("card")
        base = {"content": getattr(card, "content", {})} if card else {}
        seq = get_by_path({"$": base}, list_path) or []
    if not isinstance(seq, list):
        logger.warning(f"[节点] List.ForEach 取值非列表 path={list_path}")
        return
    # logger.info(f"[节点] List.ForEach 解析完成，长度={len(seq)}")
    for idx, it in enumerate(seq, start=1):
        state["item"] = {"index": idx, **(it if isinstance(it, dict) else {"value": it})}
        # logger.info(f"[节点] List.ForEach index={idx}")
        run_body()


@register_node("List.ForEachRange")
def node_list_foreach_range(session: Session, state: dict, params: dict, run_body):
    """
    List.ForEachRange: 根据计数遍历 1..N
    params:
      - countPath: string 例如 "$.content.stage_count"
      - start: int 默认 1
    """
    count_path = params.get("countPath")
    if not isinstance(count_path, str):
        logger.warning("[节点] List.ForEachRange 缺少 countPath")
        return
    card = state.get("card") or (state.get("current") or {}).get("card")
    base = {"content": getattr(card, "content", {})} if card else {}
    count_val = get_by_path({"$": base}, count_path) or 0
    try:
        n = int(count_val)
    except Exception:
        n = 0
    
    if n <= 0:
        # logger.info(f"[节点] List.ForEachRange 计数为 {n}，跳过循环")
        return
    
    start = int(params.get("start", 1) or 1)
    for i in range(start, start + n):
        state["item"] = {"index": i}
        # logger.info(f"[节点] List.ForEachRange index={i} (共{n}次)")
        run_body()


@register_node("Card.ClearFields")
def node_card_clear_fields(session: Session, state: Dict[str, Any], params: Dict[str, Any]) -> None:
    """
    Card.ClearFields: 清空卡片的指定字段
    参数:
    - target: 目标卡片 ID 或 '$self'
    - fields: 要清空的字段路径列表 (如 ['$.content.field1', '$.content.field2'])
    """
    target = params.get("target", "$self")
    fields = params.get("fields", [])
    
    if target == "$self":
        target_id = state["scope"].get("card_id")
    else:
        target_id = int(target) if isinstance(target, (int, str)) and str(target).isdigit() else None
    
    if not target_id:
        logger.warning(f"[Card.ClearFields] 无效的目标卡片: {target}")
        return
        
    card = get_card_by_id(session, target_id)
    if not card:
        logger.warning(f"[Card.ClearFields] 卡片不存在: {target_id}")
        return
    
    if not isinstance(fields, list) or not fields:
        logger.warning("[Card.ClearFields] 缺少有效的 fields 参数")
        return
    
    # 使用深拷贝避免修改原始对象
    content = copy.deepcopy(card.content or {})
    
    # 清空指定字段
    for field_path in fields:
        if isinstance(field_path, str) and field_path.startswith("$."):
            set_by_path({"$": content}, field_path, None)
    
    card.content = content
    session.add(card)
    session.commit()
    
    # 记录受影响的卡片
    if "touched_card_ids" in state:
        state["touched_card_ids"].add(target_id)


@register_node("Card.ReplaceFieldText")
def node_card_replace_field_text(session: Session, state: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Card.ReplaceFieldText: 替换卡片字段中的指定文本片段
    
    参数:
    - card_id: 目标卡片ID
    - field_path: 字段路径（如 "content", "overview" 等）
    - old_text: 要被替换的原文片段（必须完全匹配）
    - new_text: 新的文本内容
    
    返回:
    - success: 是否成功
    - replaced_count: 替换次数
    - old_length: 原文本长度
    - new_length: 新文本长度
    - error: 错误信息（如果失败）
    """
    card_id = params.get("card_id")
    field_path = params.get("field_path", "")
    old_text = params.get("old_text", "")
    new_text = params.get("new_text", "")
    
    if not card_id:
        return {"success": False, "error": "缺少 card_id 参数"}
    
    if not field_path:
        return {"success": False, "error": "缺少 field_path 参数"}
    
    if not old_text:
        return {"success": False, "error": "缺少 old_text 参数"}
    
    # 获取卡片
    card = get_card_by_id(session, int(card_id))
    if not card:
        return {"success": False, "error": f"卡片 {card_id} 不存在"}
    
    # 处理字段路径，标准化为 content. 前缀
    normalized_path = field_path
    if not normalized_path.startswith("content."):
        normalized_path = f"content.{normalized_path}"
    
    logger.info(f"  原始字段路径: {field_path}")
    logger.info(f"  标准化路径: {normalized_path}")
    
    # 获取字段当前值
    path_parts = normalized_path.split(".")
    logger.info(f"  路径分段: {path_parts}")
    
    current_value = card.content or {}
    logger.info(f"  card.content 类型: {type(current_value)}")
    logger.info(f"  card.content 键: {list(current_value.keys()) if isinstance(current_value, dict) else 'N/A'}")
    
    # 逐层访问到目标字段
    for i, part in enumerate(path_parts[1:]):  # 跳过 "content"
        logger.info(f"  访问层级 {i+1}: 字段 '{part}', 当前值类型 {type(current_value)}")
        if isinstance(current_value, dict):
            current_value = current_value.get(part, "")
            logger.info(f"    获取到的值长度: {len(str(current_value))}")
        else:
            return {
                "success": False,
                "error": f"字段路径 {normalized_path} 无效（在 {part} 处不是字典）"
            }
    
    # 确保当前值是字符串
    if not isinstance(current_value, str):
        return {
            "success": False,
            "error": f"字段 {field_path} 不是文本类型，无法进行文本替换"
        }
    
    # 检查是否使用模糊匹配模式（开头...结尾）
    fuzzy_match = False
    actual_old_text = old_text
    
    if "..." in old_text or "……" in old_text:
        # 模糊匹配模式：提取开头和结尾
        fuzzy_match = True
        separator = "..." if "..." in old_text else "……"
        parts = old_text.split(separator, 1)  # 只分割一次
        
        if len(parts) == 2:
            start_text = parts[0].strip()
            end_text = parts[1].strip()
            
            logger.info(f"  🔍 使用模糊匹配模式")
            logger.info(f"  开头文本: {start_text[:20]}...")
            logger.info(f"  结尾文本: ...{end_text[-20:]}")
            
            # 在内容中查找匹配的片段
            start_idx = current_value.find(start_text)
            if start_idx == -1:
                return {
                    "success": False,
                    "error": f"在字段 '{field_path}' 中未找到开头文本: {start_text[:30]}...",
                    "hint": "请确认开头文本是否完全匹配"
                }
            
            # 从开头位置之后查找结尾
            end_search_start = start_idx + len(start_text)
            end_idx = current_value.find(end_text, end_search_start)
            if end_idx == -1:
                return {
                    "success": False,
                    "error": f"在字段 '{field_path}' 中未找到结尾文本: ...{end_text[-30:]}",
                    "hint": "请确认结尾文本是否完全匹配"
                }
            
            # 提取完整的匹配片段
            actual_old_text = current_value[start_idx:end_idx + len(end_text)]
            logger.info(f"  ✅ 模糊匹配成功，找到 {len(actual_old_text)} 字符的片段")
        else:
            return {
                "success": False,
                "error": "模糊匹配格式错误，应为：开头文本...结尾文本",
                "hint": "使用三个点或六个点作为分隔符"
            }
    
    # 检查原文是否存在（精确匹配或模糊匹配后的完整文本）
    if actual_old_text not in current_value:
        preview = current_value[:100] + "..." if len(current_value) > 100 else current_value
        error_message = f"在字段 '{field_path}' 中未找到指定的原文片段"
        logger.warning(f"⚠️ 文本未找到，field_path='{field_path}'")
        return {
            "success": False,
            "error": error_message,
            "field_preview": preview,
            "hint": "请确认原文片段是否完全匹配（包括标点符号和空格、换行符）"
        }
    
    # 执行替换
    replaced_count = current_value.count(actual_old_text)
    updated_value = current_value.replace(actual_old_text, new_text)
    
    if fuzzy_match:
        logger.info(f"  📝 模糊匹配替换: 原文 {len(actual_old_text)} 字符 → 新文本 {len(new_text)} 字符")
    
    logger.info(f"[Card.ReplaceFieldText] card_id={card_id}, field={field_path}, 找到 {replaced_count} 处匹配")
    logger.info(f"  替换前长度: {len(current_value)} 字符")
    logger.info(f"  替换后长度: {len(updated_value)} 字符")
    
    # 使用深拷贝避免修改原始对象
    content = copy.deepcopy(card.content or {})
    
    # 设置更新后的值
    # 去掉 "content." 前缀，得到实际的字段路径
    field_parts = normalized_path.split(".")[1:]  # 去掉 "content"，得到 ["field"] 或 ["nested", "field"]
    
    # 逐层访问并设置值
    current_dict = content
    for part in field_parts[:-1]:
        if part not in current_dict:
            current_dict[part] = {}
        current_dict = current_dict[part]
    
    # 设置最终字段的值
    current_dict[field_parts[-1]] = updated_value
    
    card.content = content
    session.add(card)
    session.commit()
    session.refresh(card)
    
    # 记录受影响的卡片
    if "touched_card_ids" in state:
        state["touched_card_ids"].add(int(card_id))
    
    logger.info(f"[Card.ReplaceFieldText] 替换成功")
    
    return {
        "success": True,
        "card_id": card_id,
        "card_title": card.title,
        "field_path": field_path,
        "replaced_count": replaced_count,
        "old_length": len(current_value),
        "new_length": len(updated_value)
    }


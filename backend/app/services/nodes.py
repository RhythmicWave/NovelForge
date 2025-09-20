from __future__ import annotations

from typing import Any, Optional, List, Dict
import re
from sqlmodel import Session, select

from app.db.models import Card, CardType
from loguru import logger


def _get_card_by_id(session: Session, card_id: int) -> Optional[Card]:
    try:
        return session.get(Card, int(card_id))
    except Exception:
        return None


def _get_by_path(obj: Any, path: str) -> Any:
    # 极简路径解析：支持 $.content.a.b.c 与 $.a.b
    if not path or not isinstance(path, str):
        return None
    if not path.startswith("$."):
        return None
    parts = path[2:].split(".")
    # 处理根 '$'：若 obj 为 {"$": base} 则先取出 base
    if isinstance(obj, dict) and "$" in obj:
        cur: Any = obj.get("$")
    else:
        cur = obj
    for p in parts:
        if isinstance(cur, dict):
            cur = cur.get(p)
        else:
            try:
                cur = getattr(cur, p)
            except Exception:
                return None
    return cur


def _set_by_path(obj: Dict[str, Any], path: str, value: Any) -> bool:
    # 仅支持以 $. 开头的对象路径写入
    if not isinstance(obj, dict) or not isinstance(path, str) or not path.startswith("$."):
        return False
    parts = path[2:].split(".")
    cur: Dict[str, Any] = obj
    for p in parts[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]  # type: ignore[assignment]
    cur[parts[-1]] = value
    return True


_TPL_PATTERN = re.compile(r"\{([^{}]+)\}")


def _resolve_expr(expr: str, state: dict) -> Any:
    expr = expr.strip()
    # index（循环序号，从 1 开始）
    if expr == "index":
        return (state.get("item") or {}).get("index")
    # item.xxx
    if expr.startswith("item."):
        item = state.get("item") or {}
        return _get_by_path({"item": item}, "$." + expr)
    # current.xxx / current.card.xxx
    if expr.startswith("current."):
        cur = state.get("current") or {}
        return _get_by_path({"current": cur}, "$." + expr)
    # scope.xxx
    if expr.startswith("scope."):
        scope = state.get("scope") or {}
        return _get_by_path({"scope": scope}, "$." + expr)
    # $.content.xxx 针对当前 card
    if expr.startswith("$."):
        card = (state.get("current") or {}).get("card") or state.get("card")
        base = {"content": getattr(card, "content", {})} if card else {}
        return _get_by_path({"$": base}, expr)
    return None


def _to_name(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x.strip()
    if isinstance(x, dict):
        for key in ("name", "title", "label", "content"):
            v = x.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
            if isinstance(v, dict):
                nn = v.get("name") or v.get("title")
                if isinstance(nn, str) and nn.strip():
                    return nn.strip()
    return str(x).strip()


def _to_name_list(seq: Any) -> List[str]:
    if not isinstance(seq, list):
        return []
    out: List[str] = []
    for it in seq:
        name = _to_name(it)
        if name:
            out.append(name)
    # 去重保持顺序
    seen = set()
    unique: List[str] = []
    for n in out:
        if n not in seen:
            unique.append(n)
            seen.add(n)
    return unique


def _render_value(val: Any, state: dict) -> Any:
    """
    模板渲染：
    - 字符串：{item.xxx} / {current.card.content.xxx} / {scope.xxx} / {index} / {$.content.xxx}
    - 对象：支持 {"$toNameList": "item.entity_list"} 快捷转换
    - 列表/对象：递归渲染
    """
    if isinstance(val, dict):
        if "$toNameList" in val and isinstance(val.get("$toNameList"), str):
            seq = _resolve_expr(val["$toNameList"], state)
            return _to_name_list(seq)
        return {k: _render_value(v, state) for k, v in val.items()}
    if isinstance(val, list):
        return [_render_value(v, state) for v in val]
    if isinstance(val, str):
        # 单一表达式直接返回原类型
        m = _TPL_PATTERN.fullmatch(val.strip())
        if m:
            resolved = _resolve_expr(m.group(1), state)
            return resolved
        # 内嵌模板，最终还是字符串
        def repl(match: re.Match) -> str:
            expr = match.group(1)
            res = _resolve_expr(expr, state)
            if isinstance(res, (dict, list)):
                return str(res)
            return "" if res is None else str(res)
        return _TPL_PATTERN.sub(repl, val)
    return val


def _get_from_state(path_expr: Any, state: dict) -> Any:
    # 兼容 path 字符串（$. / $item(. ) / $current(. ) / $scope(. ) / item. / scope. / current.）或直接值
    if isinstance(path_expr, str):
        p = path_expr.strip()
        if p in ("item", "$item"):
            return state.get("item")
        if p in ("current", "$current"):
            return state.get("current")
        if p in ("scope", "$scope"):
            return state.get("scope")
        # 统一映射到 _resolve_expr 可识别形式
        if p.startswith("$item."):
            return _resolve_expr("item." + p[len("$item."):], state)
        if p.startswith("$current."):
            return _resolve_expr("current." + p[len("$current."):], state)
        if p.startswith("$scope."):
            return _resolve_expr("scope." + p[len("$scope."):], state)
        if p.startswith(("item.", "current.", "scope.", "$.")):
            return _resolve_expr(p, state)
    return path_expr


def node_card_read(session: Session, state: dict, params: dict) -> dict:
    """
    Card.Read: 读取锚点卡片或指定 card_id，写入 state['card'] 并返回 {'card': Card}
    params:
      - target: "$self" | int(card_id)
    """
    target = params.get("target", "$self")
    card: Optional[Card] = None
    if target == "$self":
        scope = state.get("scope") or {}
        card_id = scope.get("card_id")
        if card_id:
            card = _get_card_by_id(session, card_id)
    else:
        try:
            card = _get_card_by_id(session, int(target))
        except Exception:
            card = None
    if not card:
        raise ValueError("Card.Read 未找到目标卡片")
    state["card"] = card
    state["current"] = {"card": card}
    logger.info(f"[节点] 读取卡片 card_id={card.id} title={card.title}")
    return {"card": card}


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
        value_expr = params.get("setValue")
        value = _get_from_state(value_expr, state)
        base = dict(card.content or {})
        ok = False
        if norm_path.startswith("$.content"):
            ok = _set_by_path({"content": base}, norm_path, value)
        else:
            ok = _set_by_path(base, norm_path, value)
        if not ok and norm_path.startswith("$.content."):
            _set_by_path({"content": base}, norm_path, value)
        card.content = base
        session.add(card)
        session.commit()
        session.refresh(card)
        logger.info(f"[节点] 按路径设置内容完成 card_id={card.id} path={set_path} -> norm={norm_path}")
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
    content_merge = _render_value(content_merge, state)
    if not isinstance(content_merge, dict):
        raise ValueError("contentMerge 需为对象")
    base = dict(card.content or {})
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
    logger.info(f"[节点] 修改卡片内容完成 card_id={card.id} 合并键={list(content_merge.keys())}")
    return {"card": card}


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
    if not isinstance(parent, Card):
        # 允许未先读父卡，但要求提供 parent
        pass

    card_type_name = params.get("cardType")
    if not card_type_name:
        raise ValueError("参数 cardType 必填")
    ct: Optional[CardType] = session.exec(select(CardType).where(CardType.name == card_type_name)).first()
    if not ct:
        raise ValueError(f"未找到卡片类型: {card_type_name}")

    raw_title: Optional[str] = params.get("title")
    if not raw_title:
        title_path = params.get("titlePath")
        if isinstance(title_path, str) and title_path:
            resolved_title = _get_from_state(title_path, state)
            if isinstance(resolved_title, (str, int, float)):
                raw_title = str(resolved_title)
    title = _render_value(raw_title, state) if isinstance(raw_title, str) else raw_title
    if not isinstance(title, str) or not title.strip():
        title = ct.name or "未命名"

    # 解析 parent 目标
    parent_spec = params.get("parent", "$self")
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
        p = _get_card_by_id(session, int(parent_spec))
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
    content_merge = params.get("contentMerge") if isinstance(params.get("contentMerge"), dict) else None
    content_template = params.get("contentTemplate") if isinstance(params.get("contentTemplate"), (dict, list, str)) else None
    content_path = params.get("contentPath") if isinstance(params.get("contentPath"), str) else None
    item = state.get("item") or {}

    if use_item:
        content: Any = dict(item)
    else:
        if content_template is not None:
            content = _render_value(content_template, state)
            if not isinstance(content, dict):
                content = {"value": content}
        elif content_path:
            resolved = _get_from_state(content_path, state)
            content = resolved if isinstance(resolved, dict) else {"value": resolved}
        else:
            base = dict(target.content) if target else {}
            cm = _render_value(content_merge or {}, state)
            content = {**base, **(cm or {})}

    if target:
        target.content = content
        session.add(target)
        session.commit()
        session.refresh(target)
        result = target
        logger.info(f"[节点] 更新子卡完成 parent_id={target_parent_id} title={title} card_id={target.id}")
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
        logger.info(f"[节点] 创建子卡完成 parent_id={target_parent_id} title={title} card_id={new_card.id}")

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
        logger.info(f"[节点] List.ForEach 原始 list 参数 type={type(raw).__name__} value={raw!r}")
        if isinstance(raw, list):
            seq = raw
        elif isinstance(raw, dict):
            # 支持 { path: '$.content.xxx' }
            cand = raw.get("path") or raw.get("listPath")
            if isinstance(cand, str) and cand:
                seq = _get_from_state(cand, state)
        elif isinstance(raw, str) and raw:
            seq = _get_from_state(raw.strip(), state)
    if seq is None:
        if not isinstance(list_path, str) or not list_path:
            logger.warning("[节点] List.ForEach 缺少 listPath")
            return
        card = state.get("card") or (state.get("current") or {}).get("card")
        base = {"content": getattr(card, "content", {})} if card else {}
        seq = _get_by_path({"$": base}, list_path) or []
    if not isinstance(seq, list):
        logger.warning(f"[节点] List.ForEach 取值非列表 path={list_path}")
        return
    logger.info(f"[节点] List.ForEach 解析完成，长度={len(seq)}")
    for idx, it in enumerate(seq, start=1):
        state["item"] = {"index": idx, **(it if isinstance(it, dict) else {"value": it})}
        logger.info(f"[节点] List.ForEach index={idx}")
        run_body()


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
    count_val = _get_by_path({"$": base}, count_path) or 0
    try:
        n = int(count_val)
    except Exception:
        n = 0
    start = int(params.get("start", 1) or 1)
    for i in range(start, max(start, n) + 1):
        state["item"] = {"index": i}
        logger.info(f"[节点] List.ForEachRange index={i}/{n}")
        run_body()
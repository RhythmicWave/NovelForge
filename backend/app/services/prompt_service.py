from typing import List, Optional, Dict, Any
from sqlmodel import Session, select
from app.db.models import Prompt
from app.schemas.prompt import PromptCreate, PromptUpdate
from string import Template
import re

def get_prompt(session: Session, prompt_id: int) -> Optional[Prompt]:
    """根据ID获取单个提示词"""
    return session.get(Prompt, prompt_id)

def get_prompt_by_name(session: Session, prompt_name: str) -> Optional[Prompt]:
    """根据名称获取单个提示词"""
    statement = select(Prompt).where(Prompt.name == prompt_name)
    return session.exec(statement).first()

def get_prompts(session: Session, skip: int = 0, limit: int = 100) -> List[Prompt]:
    """获取提示词列表"""
    statement = select(Prompt).offset(skip).limit(limit)
    return session.exec(statement).all()

def create_prompt(session: Session, prompt_create: PromptCreate) -> Prompt:
    """创建新提示词"""
    # 检查名称是否已存在
    existing_prompt = get_prompt_by_name(session, prompt_create.name)
    if existing_prompt:
        raise ValueError(f"提示词名称 '{prompt_create.name}' 已存在")
    
    db_prompt = Prompt.model_validate(prompt_create)
    session.add(db_prompt)
    session.commit()
    session.refresh(db_prompt)
    return db_prompt

def update_prompt(session: Session, prompt_id: int, prompt_update: PromptUpdate) -> Optional[Prompt]:
    """更新提示词"""
    db_prompt = session.get(Prompt, prompt_id)
    if not db_prompt:
        return None
    prompt_data = prompt_update.model_dump(exclude_unset=True)
    for key, value in prompt_data.items():
        setattr(db_prompt, key, value)
    session.add(db_prompt)
    session.commit()
    session.refresh(db_prompt)
    return db_prompt

def delete_prompt(session: Session, prompt_id: int) -> bool:
    """删除提示词"""
    db_prompt = session.get(Prompt, prompt_id)
    if not db_prompt:
        return False
    session.delete(db_prompt)
    session.commit()
    return True

def render_prompt(prompt_template: str, context: Dict[str, Any]) -> str:
    """
    使用上下文渲染提示词模板。
    
    :param prompt_template: 带有占位符的字符串模板 (e.g., "你好, ${name}")
    :param context: 包含要填充到模板中的值的字典 (e.g., {"name": "世界"})
    :return: 渲染后的字符串 ("你好, 世界")
    """
    template = Template(prompt_template)
    try:
        return template.substitute(context)
    except KeyError as e:
        raise ValueError(f"渲染提示词失败：上下文中缺少变量 '{e.args[0]}'")
    except Exception as e:
        raise ValueError(f"渲染提示词时发生未知错误: {e}")


# 知识库占位符解析
_KB_ID_PATTERN = re.compile(r"@KB\{\s*id\s*=\s*(\d+)\s*\}")
_KB_NAME_PATTERN = re.compile(r"@KB\{\s*name\s*=\s*([^}]+)\}")


def inject_knowledge(session: Session, template: str) -> str:
    """将模板中的知识库占位符注入为实际内容
    
    规则：
    1) 对 "- knowledge:" 段落内的多个占位符，按顺序注入并以编号分隔：
       - knowledge:\n1.\n<KB1>\n\n2.\n<KB2> ...
    2) knowledge 段之外若出现占位符，做就地替换为知识全文。
    3) 若找不到对应知识库，保留提示注释，避免中断。
    
    Args:
        session: 数据库会话
        template: 提示词模板
        
    Returns:
        注入知识库后的模板
    """
    from app.services.knowledge_service import KnowledgeService
    
    svc = KnowledgeService(session)

    def fetch_kb_by_id(kid: int) -> str:
        kb = svc.get_by_id(kid)
        return kb.content if kb and kb.content else f"/* 知识库未找到: id={kid} */"

    def fetch_kb_by_name(name: str) -> str:
        kb = svc.get_by_name(name)
        return kb.content if kb and kb.content else f"/* 知识库未找到: name={name} */"

    # 先处理 knowledge 分段（更结构化的注入）
    lines = template.splitlines()
    i = 0
    out_lines: list[str] = []
    while i < len(lines):
        line = lines[i]
        # 匹配顶级的 "- knowledge:" 行（大小写不敏感）
        if re.match(r"^\s*-\s*knowledge\s*:\s*$", line, flags=re.IGNORECASE):
            # 收集该段落内的占位符行，直到遇到下一个顶级 "- <Something>" 行或文件结尾
            j = i + 1
            block_lines: list[str] = []
            while j < len(lines) and not re.match(r"^\s*-\s*\w", lines[j]):
                block_lines.append(lines[j])
                j += 1
            # 提取占位符顺序
            placeholders: list[tuple[str, str]] = []  # (mode, value)
            for bl in block_lines:
                for m in _KB_ID_PATTERN.finditer(bl):
                    placeholders.append(("id", m.group(1)))
                for m in _KB_NAME_PATTERN.finditer(bl):
                    placeholders.append(("name", m.group(1).strip().strip('\"\'')))
            # 构建编号内容
            out_lines.append(line)  # 保留标题行 "- knowledge:"
            if placeholders:
                for idx, (mode, val) in enumerate(placeholders, start=1):
                    out_lines.append(f"{idx}.")
                    if mode == "id":
                        try:
                            content = fetch_kb_by_id(int(val))
                        except Exception:
                            content = f"/* 知识库未找到: id={val} */"
                    else:
                        content = fetch_kb_by_name(val)
                    out_lines.append(content.strip())
                    # 段落间空行
                    if idx < len(placeholders):
                        out_lines.append("")
            # 跳过原 block
            i = j
            continue
        else:
            out_lines.append(line)
            i += 1

    enumerated_text = "\n".join(out_lines)

    # knowledge 段之外的就地替换（若仍有占位符残留）
    def repl_id(m: re.Match) -> str:
        try:
            kid = int(m.group(1))
        except Exception:
            return f"/* 知识库未找到: id={m.group(1)} */"
        return fetch_kb_by_id(kid)

    def repl_name(m: re.Match) -> str:
        name = m.group(1).strip().strip('\"\'')
        return fetch_kb_by_name(name)

    result = _KB_ID_PATTERN.sub(repl_id, enumerated_text)
    result = _KB_NAME_PATTERN.sub(repl_name, result)
    return result 
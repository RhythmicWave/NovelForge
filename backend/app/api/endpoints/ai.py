from fastapi import APIRouter, Depends, HTTPException, Body
from sqlmodel import Session, select
from app.db.session import get_session
from app.schemas.ai import ContinuationRequest, ContinuationResponse, GeneralAIRequest
from app.schemas.response import ApiResponse
from app.services import prompt_service, agent_service, llm_config_service
from fastapi.responses import StreamingResponse
import json
from fastapi import Body
from pydantic import ValidationError, create_model
from pydantic import Field as PydanticField
from typing import Type, Dict, Any, List

from app.db.models import OutputModel, Card, CardType
from copy import deepcopy

# 引入知识库
from app.services.knowledge_service import KnowledgeService
import re
from app.schemas.entity import DYNAMIC_INFO_TYPES
from app.schemas import entity as entity_schemas

router = APIRouter()

# --- JSON Schema → Python 类型简易映射（尽量保守，无法解析的情况回退为 Any） ---
from typing import Any as _Any, Dict as _Dict, List as _List

def _json_schema_to_py_type(sch: Dict[str, Any]) -> Any:
    if not isinstance(sch, dict):
        return _Any
    if '$ref' in sch:
        # 简化处理：引用统一按对象处理
        return _Dict[str, _Any]
    t = sch.get('type')
    if t == 'string':
        return str
    if t == 'integer':
        return int
    if t == 'number':
        return float
    if t == 'boolean':
        return bool
    if t == 'array':
        item_sch = sch.get('items') or {}
        return _List[_json_schema_to_py_type(item_sch)]  # type: ignore[index]
    if t == 'object':
        # 若有 properties 但为动态结构，这里按 Dict 处理
        return _Dict[str, _Any]
    # 未声明 type 或无法识别
    return _Any


def _build_model_from_json_schema(model_name: str, schema: Dict[str, Any]):
    props: Dict[str, Any] = (schema or {}).get('properties') or {}
    required: List[str] = list((schema or {}).get('required') or [])
    field_defs: Dict[str, tuple] = {}
    for fname, fsch in props.items():
        anno = _json_schema_to_py_type(fsch if isinstance(fsch, dict) else {})
        desc = fsch.get('description') if isinstance(fsch, dict) else None
        is_required = fname in required
        if desc is not None:
            default_val = PydanticField(... if is_required else None, description=desc)
        else:
            default_val = ... if is_required else None
        field_defs[fname] = (anno, default_val)
    return create_model(model_name, **field_defs)

# --- Schema $defs 递归补全（将内置模型的 $defs 注入自定义 Schema） ---
_BUILTIN_DEFS_CACHE: Dict[str, Any] | None = None

def _get_builtin_defs() -> Dict[str, Any]:
    global _BUILTIN_DEFS_CACHE
    if _BUILTIN_DEFS_CACHE is not None:
        return _BUILTIN_DEFS_CACHE
    merged: Dict[str, Any] = {}
    for _, model_class in RESPONSE_MODEL_MAP.items():
        sch = model_class.model_json_schema(ref_template="#/$defs/{model}")
        defs = sch.get('$defs') or {}
        merged.update(defs)
    _BUILTIN_DEFS_CACHE = merged
    return merged

def _collect_ref_names(node: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(node, dict):
        if '$ref' in node and isinstance(node['$ref'], str) and node['$ref'].startswith('#/$defs/'):
            names.add(node['$ref'].split('/')[-1])
        for v in node.values():
            names |= _collect_ref_names(v)
    elif isinstance(node, list):
        for it in node:
            names |= _collect_ref_names(it)
    return names

def _augment_schema_with_builtin_defs(schema: Dict[str, Any]) -> Dict[str, Any]:
    # 不修改原对象
    sch = deepcopy(schema) if schema is not None else {}
    if not isinstance(sch, dict):
        return sch
    sch.setdefault('$defs', {})
    defs = sch['$defs']
    builtin_defs = _get_builtin_defs()

    # 迭代补全，直到无新引用
    seen: set[str] = set(defs.keys())
    pending = _collect_ref_names(sch) - seen
    while pending:
        name = pending.pop()
        if name in defs:
            continue
        if name in builtin_defs:
            defs[name] = deepcopy(builtin_defs[name])
            # 新增定义中可能还引用其他 defs
            newly = _collect_ref_names(defs[name]) - set(defs.keys())
            pending |= newly
        # 若找不到该定义，则跳过（保持原样，让 LLM 容忍）
    return sch

# 响应模型映射表（内置）
from app.schemas.response_registry import RESPONSE_MODEL_MAP

# 知识库占位符解析与替换
_KB_ID_PATTERN = re.compile(r"@KB\{\s*id\s*=\s*(\d+)\s*\}")
_KB_NAME_PATTERN = re.compile(r"@KB\{\s*name\s*=\s*([^}]+)\}")


def _inject_knowledge(session: Session, template: str) -> str:
    """将模板中的知识库占位符注入为实际内容。

    规则：
    1) 对 "- knowledge:" 段落内的多个占位符，按顺序注入并以编号分隔：
       - knowledge:\n1.\n<KB1>\n\n2.\n<KB2> ...
    2) knowledge 段之外若出现占位符，做就地替换为知识全文。
    3) 若找不到对应知识库，保留提示注释，避免中断。
    """
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

@router.get("/schemas", response_model=Dict[str, Any], summary="获取所有输出模型的JSON Schema（内置+自定义）")
def get_all_schemas(session: Session = Depends(get_session)):
    """返回内置模型和数据库 OutputModel 的 schema 聚合，键为模型名称。"""
    all_definitions: Dict[str, Any] = {}

    # 1) 内置 pydantic 模型
    for name, model_class in RESPONSE_MODEL_MAP.items():
        schema = model_class.model_json_schema(ref_template="#/$defs/{model}")
        if '$defs' in schema:
            # 合并依赖到主表；移除自身 $defs，提高前端解析简洁性
            all_definitions.update(schema['$defs'])
            del schema['$defs']
        all_definitions[name] = schema

    # --- 动态修复：将 CharacterCard.dynamic_info 从 Dict 展开为显式 properties（按枚举值），便于前端解析 ---
    try:
        cc = all_definitions.get('CharacterCard')
        if isinstance(cc, dict):
            props = (cc.get('properties') or {})
            if 'dynamic_info' in props:
                # 内联 DynamicInfoItem 结构，避免 $defs 引用导致前端解析困难
                item_schema = {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "info": {"type": "string"},
                        "weight": {"type": "number"}
                    },
                    "required": ["id", "info", "weight"]
                }
                enum_values = DYNAMIC_INFO_TYPES
                props['dynamic_info'] = {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        ev: {"type": "array", "items": item_schema} for ev in enum_values
                    },
                    "description": "角色动态信息，按类别分组的数组（键为中文枚举值）"
                }
                cc['properties'] = props
                all_definitions['CharacterCard'] = cc
    except Exception:
        pass

    # 2) 数据库输出模型
    db_models = session.exec(select(OutputModel)).all()
    for om in db_models:
        if om.json_schema:
            # 返回时对 DB 模型做 $defs 递归补全，便于前端解析嵌入-嵌入结构
            all_definitions[om.name] = _augment_schema_with_builtin_defs(om.json_schema)

    # 3) 注入 entity 动态信息相关模型（用于前端解析 $ref: DynamicInfo 等）
    try:
        entity_models = [
            entity_schemas.DynamicInfoItem,
            entity_schemas.DynamicInfo,
            entity_schemas.UpdateDynamicInfo,

        ]
        for mdl in entity_models:
            sch = mdl.model_json_schema(ref_template="#/$defs/{model}")
            if '$defs' in sch:
                all_definitions.update(sch['$defs'])
                del sch['$defs']
            all_definitions[mdl.__name__] = sch
    except Exception:
        pass

    return all_definitions

@router.get("/content-models", response_model=List[str], summary="获取所有可用输出模型名称")
def get_content_models(session: Session = Depends(get_session)):
    names = list(RESPONSE_MODEL_MAP.keys())
    db_models = session.exec(select(OutputModel.name)).all()
    for n in db_models:
        if n not in names:
            names.append(n)
    return names


async def stream_wrapper(generator):
    async for item in generator:
        yield f"data: {json.dumps({'content': item})}\n\n"

@router.get("/config-options", summary="获取AI生成配置选项")
async def get_ai_config_options(session: Session = Depends(get_session)):
    """获取AI生成时可用的配置选项"""
    try:
        # 获取所有LLM配置
        llm_configs = llm_config_service.get_llm_configs(session)
        # 获取所有提示词
        prompts = prompt_service.get_prompts(session)
        # 响应模型来自内置 + OutputModel
        response_models = get_content_models(session)
        return ApiResponse(data={
            "llm_configs": [{"id": config.id, "display_name": config.display_name or config.model_name} for config in llm_configs],
            "prompts": [{"id": prompt.id, "name": prompt.name, "description": prompt.description, "built_in": getattr(prompt, 'built_in', False)} for prompt in prompts],
            "available_tasks": [],
            "response_models": response_models
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取配置选项失败: {str(e)}")

@router.post("/generate", summary="通用AI生成接口")
async def generate_ai_content(
    request: GeneralAIRequest = Body(...),
    session: Session = Depends(get_session),
):
    """
    一个通用的AI内容生成端点。
    它接收一个输入、LLM配置、提示词和响应模型，然后返回结构化的输出。
    """
    # 验证必要的参数
    if not all([request.input, request.llm_config_id, request.prompt_name, request.response_model_name]):
        raise HTTPException(status_code=400, detail="缺少必要的生成参数: input, llm_config_id, prompt_name, 或 response_model_name")

    # 解析响应模型（保持原有实现）
    resp_model = None
    schema_for_prompt: Dict[str, Any] | None = None
    # 1) 优先动态 schema
    if request.response_model_schema:
        try:
            resp_model = _build_model_from_json_schema('DynamicResponseModel', request.response_model_schema)
            # system_prompt 使用“原始 schema”确保与训练一致
            schema_for_prompt = _augment_schema_with_builtin_defs(request.response_model_schema)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"动态创建模型失败: {e}")
    else:
        # 2) 尝试内置
        built_in = RESPONSE_MODEL_MAP.get(request.response_model_name) if isinstance(request.response_model_name, str) else None
        if built_in is not None:
            resp_model = built_in
            schema_for_prompt = built_in.model_json_schema()
        else:
            # 3) 数据库 OutputModel
            om = session.exec(select(OutputModel).where(OutputModel.name == request.response_model_name)).first() if isinstance(request.response_model_name, str) else None
            if not om or not om.json_schema:
                raise HTTPException(status_code=400, detail=f"未找到响应模型: {request.response_model_name}")
            try:
                resp_model = _build_model_from_json_schema('DbResponseModel', om.json_schema)
                # system_prompt 使用：补全后的 DB Schema
                schema_for_prompt = _augment_schema_with_builtin_defs(om.json_schema)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"根据数据库Schema创建模型失败: {e}")

    # 获取提示词
    prompt = prompt_service.get_prompt_by_name(session, request.prompt_name)
    if not prompt:
        raise HTTPException(status_code=400, detail=f"未找到提示词名称: {request.prompt_name}")

    # 注入知识库占位符
    prompt_template = _inject_knowledge(session, prompt.template or '')

    # 准备 System Prompt：把 schema 发送给 LLM（尽量使用原始 JSON Schema，保持训练一致性）
    schema_json = json.dumps(schema_for_prompt if schema_for_prompt is not None else resp_model.model_json_schema(), indent=2, ensure_ascii=False)
    system_prompt = (
        f"{prompt_template}\n\n"
        f"```json\n{schema_json}\n```"
    )

    user_prompt = request.input['input_text']

    # 直接透传前端提供的 deps（JSON 字符串或 None）
    deps_str = request.deps or ""

    result = await agent_service.run_llm_agent(
        session=session,
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        output_type=resp_model,
        llm_config_id=request.llm_config_id, 
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        timeout=request.timeout,
        deps=deps_str,
    )
    return ApiResponse(data=result)

@router.post("/generate/continuation", 
             response_model=ApiResponse[ContinuationResponse], 
             summary="续写正文",
             responses={
                 200: {
                     "content": {
                         "application/json": {},
                         "text/event-stream": {}
                     },
                     "description": "成功返回续写结果或事件流"
                 }
             })
async def generate_continuation(
    request: ContinuationRequest,
    session: Session = Depends(get_session),
):
    try:
        # 强制从 prompt_name 读取模板作为 system prompt
        if not request.prompt_name:
            raise HTTPException(status_code=400, detail="续写必须指定 prompt_name")
        p = prompt_service.get_prompt_by_name(session, request.prompt_name)
        if not p or not p.template:
            raise HTTPException(status_code=400, detail=f"未找到提示词名称: {request.prompt_name}")
        # 注入知识库
        system_prompt = _inject_knowledge(session, str(p.template))

        if request.stream:
            stream_generator = agent_service.generate_continuation_streaming(session, request, system_prompt)
            return StreamingResponse(stream_wrapper(stream_generator), media_type="text/event-stream")
        else:
            result = await agent_service.generate_continuation(session, request, system_prompt)
            return ApiResponse(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

from app.schemas.wizard import Tags as _Tags
@router.get("/models/tags", response_model=_Tags, summary="导出 Tags 模型（用于类型生成）")
def export_tags_model():
    return _Tags() 
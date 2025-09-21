
from sqlmodel import Session, select
from app.db.models import LLMConfig
from app.schemas.llm_config import LLMConfigCreate, LLMConfigUpdate

def create_llm_config(session: Session, config_in: LLMConfigCreate) -> LLMConfig:
    # 现在直接使用 config_in 创建模型，它会包含 api_key
    db_config = LLMConfig.model_validate(config_in)
    
    session.add(db_config)
    session.commit()
    session.refresh(db_config)
    return db_config

def get_llm_configs(session: Session) -> list[LLMConfig]:
    return session.exec(select(LLMConfig)).all()

def get_llm_config(session: Session, config_id: int) -> LLMConfig | None:
    return session.get(LLMConfig, config_id)

def update_llm_config(session: Session, config_id: int, config_in: LLMConfigUpdate) -> LLMConfig | None:
    db_config = session.get(LLMConfig, config_id)
    if not db_config:
        return None
    
    # 直接更新数据，不再排除 api_key
    update_data = config_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_config, key, value)
    
    session.add(db_config)
    session.commit()
    session.refresh(db_config)
    return db_config

def delete_llm_config(session: Session, config_id: int) -> bool:
    db_config = session.get(LLMConfig, config_id)
    if not db_config:
        return False
    
    session.delete(db_config)
    session.commit()
    return True 


def can_consume(session: Session, config_id: int, need_input_tokens: int, need_output_tokens: int = 0, need_calls: int = 1) -> tuple[bool, str]:
    cfg = session.get(LLMConfig, config_id)
    if not cfg:
        return False, "LLM 配置不存在"
    # token 限额（-1 不限）
    total_need = max(0, need_input_tokens) + max(0, need_output_tokens)
    if cfg.token_limit is not None and cfg.token_limit >= 0:
        if (cfg.used_tokens_input + cfg.used_tokens_output + total_need) > cfg.token_limit:
            return False, "已超出 Token 上限"
    # 调用次数
    if cfg.call_limit is not None and cfg.call_limit >= 0:
        if (cfg.used_calls + need_calls) > cfg.call_limit:
            return False, "已超出调用次数上限"
    return True, "OK"


def accumulate_usage(session: Session, config_id: int, add_input_tokens: int, add_output_tokens: int, add_calls: int, aborted: bool = False) -> None:
    cfg = session.get(LLMConfig, config_id)
    if not cfg:
        return
    # 任务无论正常或中止，调用计数加一（也可按需区分）
    cfg.used_calls = (cfg.used_calls or 0) + max(0, add_calls)
    cfg.used_tokens_input = (cfg.used_tokens_input or 0) + max(0, add_input_tokens)
    cfg.used_tokens_output = (cfg.used_tokens_output or 0) + max(0, add_output_tokens)
    session.add(cfg)
    session.commit()


def reset_usage(session: Session, config_id: int) -> bool:
    cfg = session.get(LLMConfig, config_id)
    if not cfg:
        return False
    cfg.used_tokens_input = 0
    cfg.used_tokens_output = 0
    cfg.used_calls = 0
    session.add(cfg)
    session.commit()
    return True
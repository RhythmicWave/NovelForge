
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
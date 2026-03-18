from urllib.parse import urljoin

from sqlmodel import Session, select

from app.db.models import LLMConfig
from app.schemas.llm_config import LLMConfigCreate, LLMConfigUpdate


def _normalize_protocol(value: str | None) -> str:
    protocol = (value or "chat_completions").strip().lower()
    if protocol == "auto":
        return "chat_completions"
    return protocol if protocol in {"chat_completions", "responses"} else "chat_completions"


def normalize_api_base(api_base: str | None, base_url: str | None = None, provider: str | None = None) -> str | None:
    normalized = (api_base or base_url or "").strip()
    if normalized:
        return normalized.rstrip("/")
    if (provider or "").strip().lower() == "openai":
        return "https://api.openai.com/v1"
    return None


def _normalize_path(value: str | None, default_path: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return default_path
    return raw if raw.startswith("/") else f"/{raw}"


def resolve_transport_settings(
    *,
    provider: str | None,
    api_base: str | None,
    base_url: str | None = None,
    api_protocol: str | None = None,
    custom_request_path: str | None = None,
    models_path: str | None = None,
    user_agent: str | None = None,
) -> dict:
    normalized_base = normalize_api_base(api_base, base_url, provider)
    normalized_protocol = _normalize_protocol(api_protocol)
    normalized_custom_path = _normalize_path(custom_request_path, "") if custom_request_path else None
    normalized_models_path = _normalize_path(models_path, "/models")
    headers = {}
    if (user_agent or "").strip():
        headers["User-Agent"] = user_agent.strip()

    request_base = normalized_base
    if normalized_base and normalized_custom_path:
        request_base = urljoin(f"{normalized_base.rstrip('/')}/", normalized_custom_path.lstrip("/"))

    models_url = None
    if normalized_base:
        models_url = urljoin(f"{normalized_base.rstrip('/')}/", normalized_models_path.lstrip("/"))

    use_responses_api = normalized_protocol == "responses"

    return {
        "provider": (provider or "").strip().lower(),
        "api_base": normalized_base,
        "api_protocol": normalized_protocol,
        "custom_request_path": normalized_custom_path,
        "models_path": normalized_models_path,
        "models_url": models_url,
        "request_base": request_base,
        "user_agent": (user_agent or "").strip() or None,
        "default_headers": headers,
        "use_responses_api": use_responses_api,
    }


def _sync_legacy_base_url(db_config: LLMConfig) -> None:
    # Keep `base_url` as legacy alias only; new code reads/writes `api_base`.
    if not db_config.api_base and db_config.base_url:
        db_config.api_base = db_config.base_url
    if db_config.api_base:
        db_config.base_url = db_config.api_base
    db_config.api_protocol = _normalize_protocol(getattr(db_config, "api_protocol", None))


def _normalize_integral_fields(db_config: LLMConfig) -> None:
    integral_fields = (
        "token_limit",
        "call_limit",
        "rpm_limit",
        "tpm_limit",
        "used_tokens_input",
        "used_tokens_output",
        "used_calls",
    )
    for field_name in integral_fields:
        value = getattr(db_config, field_name, None)
        if value is None:
            continue
        if isinstance(value, bool):
            setattr(db_config, field_name, int(value))
            continue
        if isinstance(value, float):
            setattr(db_config, field_name, int(round(value)))
            continue
        if not isinstance(value, int):
            try:
                setattr(db_config, field_name, int(value))
            except (TypeError, ValueError):
                continue


def create_llm_config(session: Session, config_in: LLMConfigCreate) -> LLMConfig:
    db_config = LLMConfig.model_validate(config_in)
    _sync_legacy_base_url(db_config)
    _normalize_integral_fields(db_config)
    session.add(db_config)
    session.commit()
    session.refresh(db_config)
    return db_config


def get_llm_configs(session: Session) -> list[LLMConfig]:
    configs = session.exec(select(LLMConfig)).all()
    for cfg in configs:
        _sync_legacy_base_url(cfg)
        _normalize_integral_fields(cfg)
    return configs


def get_llm_config(session: Session, config_id: int) -> LLMConfig | None:
    cfg = session.get(LLMConfig, config_id)
    if cfg:
        _sync_legacy_base_url(cfg)
        _normalize_integral_fields(cfg)
    return cfg


def update_llm_config(session: Session, config_id: int, config_in: LLMConfigUpdate) -> LLMConfig | None:
    db_config = session.get(LLMConfig, config_id)
    if not db_config:
        return None

    update_data = config_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_config, key, value)
    _sync_legacy_base_url(db_config)
    _normalize_integral_fields(db_config)

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


def can_consume(
    session: Session,
    config_id: int,
    need_input_tokens: int,
    need_output_tokens: int = 0,
    need_calls: int = 1,
) -> tuple[bool, str]:
    cfg = session.get(LLMConfig, config_id)
    if not cfg:
        return False, "LLM 配置不存在"
    total_need = max(0, need_input_tokens) + max(0, need_output_tokens)
    if cfg.token_limit is not None and cfg.token_limit >= 0:
        if (cfg.used_tokens_input + cfg.used_tokens_output + total_need) > cfg.token_limit:
            return False, "已超出 Token 上限"
    if cfg.call_limit is not None and cfg.call_limit >= 0:
        if (cfg.used_calls + need_calls) > cfg.call_limit:
            return False, "已超出调用次数上限"
    return True, "OK"


def accumulate_usage(
    session: Session,
    config_id: int,
    add_input_tokens: int,
    add_output_tokens: int,
    add_calls: int,
    aborted: bool = False,
) -> None:
    cfg = session.get(LLMConfig, config_id)
    if not cfg:
        return
    cfg.used_calls = int(round((cfg.used_calls or 0) + max(0, add_calls)))
    cfg.used_tokens_input = int(round((cfg.used_tokens_input or 0) + max(0, add_input_tokens)))
    cfg.used_tokens_output = int(round((cfg.used_tokens_output or 0) + max(0, add_output_tokens)))
    _normalize_integral_fields(cfg)
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


def copy_llm_config(session: Session, config_id: int) -> LLMConfig | None:
    source_config = session.get(LLMConfig, config_id)
    if not source_config:
        return None

    transport = resolve_transport_settings(
        provider=source_config.provider,
        api_base=source_config.api_base,
        base_url=source_config.base_url,
        api_protocol=getattr(source_config, "api_protocol", None),
        custom_request_path=getattr(source_config, "custom_request_path", None),
        models_path=getattr(source_config, "models_path", None),
        user_agent=getattr(source_config, "user_agent", None),
    )

    new_config = LLMConfig(
        provider=source_config.provider,
        display_name=(
            f"{source_config.display_name or source_config.model_name} (副本)"
            if source_config.display_name
            else f"{source_config.model_name} (副本)"
        ),
        model_name=source_config.model_name,
        api_base=transport["api_base"],
        api_key=source_config.api_key,
        api_protocol=transport["api_protocol"],
        custom_request_path=transport["custom_request_path"],
        models_path=transport["models_path"],
        user_agent=transport["user_agent"],
        base_url=transport["api_base"],
        token_limit=source_config.token_limit,
        call_limit=source_config.call_limit,
        rpm_limit=source_config.rpm_limit,
        tpm_limit=source_config.tpm_limit,
        used_tokens_input=0,
        used_tokens_output=0,
        used_calls=0,
    )
    _normalize_integral_fields(new_config)

    session.add(new_config)
    session.commit()
    session.refresh(new_config)
    return new_config

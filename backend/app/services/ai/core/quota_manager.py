"""LLM配额管理

负责配额预检和使用统计记录。
"""

from typing import Tuple
from sqlmodel import Session
from loguru import logger

from app.services import llm_config_service


def precheck_quota(
    session: Session,
    llm_config_id: int,
    input_tokens: int,
    need_calls: int = 1
) -> Tuple[bool, str]:
    """预检配额是否足够
    
    Args:
        session: 数据库会话
        llm_config_id: LLM配置ID
        input_tokens: 预计输入token数
        need_calls: 预计调用次数
        
    Returns:
        (是否通过, 原因说明)
    """
    return llm_config_service.can_consume(
        session, llm_config_id, input_tokens, 0, need_calls
    )


def record_usage(
    session: Session,
    llm_config_id: int,
    input_tokens: int,
    output_tokens: int,
    calls: int = 1,
    aborted: bool = False
) -> None:
    """记录LLM使用情况
    
    Args:
        session: 数据库会话
        llm_config_id: LLM配置ID
        input_tokens: 实际输入token数
        output_tokens: 实际输出token数
        calls: 调用次数
        aborted: 是否被中止
    """
    try:
        llm_config_service.accumulate_usage(
            session, llm_config_id,
            max(0, input_tokens),
            max(0, output_tokens),
            max(0, calls),
            aborted=aborted
        )
    except Exception as e:
        logger.warning(f"记录LLM统计失败: {e}")

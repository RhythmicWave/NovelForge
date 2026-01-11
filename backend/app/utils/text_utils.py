"""文本处理工具

纯函数实现，无外部依赖。
"""


def truncate_text(text: str, limit: int, suffix: str = "\n...[已截断]") -> str:
    """截断文本到指定长度
    
    Args:
        text: 待截断的文本
        limit: 最大长度
        suffix: 截断后缀
        
    Returns:
        截断后的文本
    """
    if len(text) <= limit:
        return text
    # 预留suffix长度，避免截断后超出limit
    truncate_at = max(0, limit - len(suffix))
    return text[:truncate_at] + suffix

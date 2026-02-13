"""Token估算工具

纯函数实现，无外部依赖。
"""

import re
from typing import Optional

_TOKEN_REGEX = re.compile(
    r"""
    ([A-Za-z]+)               # 英文单词（连续字母算1）
    |([0-9])                 # 1个数字算1
    |([\u4E00-\u9FFF])       # 单个中文汉字算1
    |(\S)                     # 其它非空白符号/标点算1
    """,
    re.VERBOSE,
)


def estimate_tokens(text: str) -> int:
    """估算token数量
    
    规则：
    - 1个中文 = 1 token
    - 1个英文单词 = 1 token
    - 1个数字 = 1 token
    - 1个符号 = 1 token
    - 空白不计
    
    Args:
        text: 待估算的文本
        
    Returns:
        估算的token数量
    """
    if not text:
        return 0
    try:
        return sum(1 for _ in _TOKEN_REGEX.finditer(text))
    except Exception:
        # 退化方案：按非空白字符计数
        return sum(1 for ch in text if not ch.isspace())


def calc_input_tokens(system_prompt: Optional[str], user_prompt: Optional[str]) -> int:
    """计算输入token总数
    
    Args:
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        
    Returns:
        总token数
    """
    sys_part = system_prompt or ""
    usr_part = user_prompt or ""
    return estimate_tokens(sys_part + usr_part)

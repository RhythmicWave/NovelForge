"""表达式系统

安全的表达式求值器，支持：
- 基于AST的安全解析
- 白名单函数
- 类型约束
- 路径访问（JSONPath风格）
"""

from .evaluator import ExpressionEvaluator, evaluate_expression
from .functions import register_function, get_builtin_functions
from .validator import validate_expression

__all__ = [
    "ExpressionEvaluator",
    "evaluate_expression",
    "register_function",
    "get_builtin_functions",
    "validate_expression",
]

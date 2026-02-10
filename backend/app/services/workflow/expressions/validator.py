"""表达式验证器（与执行引擎同源规则）"""

from typing import List

from .evaluator import validate_expression_syntax


class ExpressionValidator:
    """表达式验证器"""

    def validate(self, expression: str) -> List[str]:
        return validate_expression_syntax(expression)


def validate_expression(expression: str) -> List[str]:
    """便捷函数：验证表达式"""
    validator = ExpressionValidator()
    return validator.validate(expression)


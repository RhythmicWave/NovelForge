"""表达式验证器"""

import ast
from typing import List, Set


class ExpressionValidator:
    """表达式验证器 - 检查表达式是否安全"""
    
    # 允许的节点类型
    ALLOWED_NODES = {
        ast.Expression,
        ast.Constant,
        ast.Name,
        ast.Load,
        ast.Store,
        ast.BinOp,
        ast.UnaryOp,
        ast.Compare,
        ast.BoolOp,
        ast.Attribute,
        ast.Subscript,
        ast.Call,
        ast.List,
        ast.Tuple,
        ast.Dict,
        ast.IfExp,
        ast.ListComp,
        ast.comprehension,
        # 运算符
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.FloorDiv,
        ast.Mod,
        ast.Pow,
        ast.UAdd,
        ast.USub,
        ast.Not,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.In,
        ast.NotIn,
        ast.Is,
        ast.IsNot,
        ast.And,
        ast.Or,
    }
    
    # 禁止的节点类型（明确列出以提供更好的错误信息）
    FORBIDDEN_NODES = {
        ast.Import: "禁止导入模块",
        ast.ImportFrom: "禁止导入模块",
        ast.FunctionDef: "禁止定义函数",
        ast.AsyncFunctionDef: "禁止定义异步函数",
        ast.ClassDef: "禁止定义类",
        ast.Delete: "禁止删除操作",
        ast.Assign: "禁止赋值操作",
        ast.AugAssign: "禁止增强赋值",
        ast.AnnAssign: "禁止注解赋值",
        ast.For: "禁止for循环",
        ast.AsyncFor: "禁止异步for循环",
        ast.While: "禁止while循环",
        ast.If: "禁止if语句（使用三元表达式代替）",
        ast.With: "禁止with语句",
        ast.AsyncWith: "禁止异步with语句",
        ast.Raise: "禁止抛出异常",
        ast.Try: "禁止try语句",
        ast.Assert: "禁止断言",
        ast.Global: "禁止global声明",
        ast.Nonlocal: "禁止nonlocal声明",
        ast.Expr: "禁止表达式语句",
        ast.Pass: "禁止pass语句",
        ast.Break: "禁止break语句",
        ast.Continue: "禁止continue语句",
    }
    
    def validate(self, expression: str) -> List[str]:
        """验证表达式
        
        Args:
            expression: 表达式字符串
            
        Returns:
            错误列表（空列表表示验证通过）
        """
        errors = []
        
        if not expression or not isinstance(expression, str):
            errors.append("表达式不能为空")
            return errors
        
        try:
            # 解析AST
            tree = ast.parse(expression, mode='eval')
            
            # 检查节点
            self._check_nodes(tree, errors)
            
        except SyntaxError as e:
            errors.append(f"语法错误: {e.msg}")
        except Exception as e:
            errors.append(f"解析失败: {str(e)}")
        
        return errors
    
    def _check_nodes(self, tree: ast.AST, errors: List[str]) -> None:
        """递归检查所有节点"""
        for node in ast.walk(tree):
            node_type = type(node)
            
            # 检查是否在禁止列表中
            if node_type in self.FORBIDDEN_NODES:
                errors.append(self.FORBIDDEN_NODES[node_type])
                continue
            
            # 检查是否在允许列表中
            if node_type not in self.ALLOWED_NODES:
                errors.append(f"不允许的节点类型: {node_type.__name__}")


def validate_expression(expression: str) -> List[str]:
    """便捷函数：验证表达式
    
    Args:
        expression: 表达式字符串
        
    Returns:
        错误列表（空列表表示验证通过）
    """
    validator = ExpressionValidator()
    return validator.validate(expression)

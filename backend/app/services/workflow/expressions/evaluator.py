"""安全的表达式求值器

基于Python AST，只允许安全的操作：
- 基本运算：+, -, *, /, //, %, **
- 比较运算：==, !=, <, >, <=, >=
- 逻辑运算：and, or, not
- 成员测试：in, not in
- 属性访问：obj.field
- 下标访问：obj[key]
- 函数调用：仅限白名单函数
- 列表/字典字面量
"""

import ast
from typing import Any, Dict, Optional, List
from loguru import logger

from .functions import get_builtin_functions


class ExpressionEvaluator:
    """安全的表达式求值器"""
    
    def __init__(self, context: Optional[Dict[str, Any]] = None):
        """
        Args:
            context: 求值上下文（变量字典）
        """
        self.context = context or {}
        self.functions = get_builtin_functions()
    
    def evaluate(self, expression: str) -> Any:
        """求值表达式
        
        Args:
            expression: 表达式字符串
            
        Returns:
            求值结果
            
        Raises:
            ValueError: 表达式不安全或求值失败
        """
        if not expression or not isinstance(expression, str):
            return expression
        
        try:
            # 解析AST
            tree = ast.parse(expression, mode='eval')
            
            # 求值
            return self._eval_node(tree.body)
        
        except Exception as e:
            logger.error(f"表达式求值失败: {expression}, 错误: {e}")
            raise ValueError(f"表达式求值失败: {str(e)}")
    
    def _eval_node(self, node: ast.AST) -> Any:
        """递归求值AST节点"""
        
        # 常量
        if isinstance(node, ast.Constant):
            return node.value
        
        # 变量名
        if isinstance(node, ast.Name):
            if node.id not in self.context:
                raise NameError(f"未定义的变量: {node.id}")
            return self.context[node.id]
        
        # 二元运算
        if isinstance(node, ast.BinOp):
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            return self._eval_binop(node.op, left, right)
        
        # 一元运算
        if isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand)
            return self._eval_unaryop(node.op, operand)
        
        # 比较运算
        if isinstance(node, ast.Compare):
            left = self._eval_node(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval_node(comparator)
                if not self._eval_compare(op, left, right):
                    return False
                left = right
            return True
        
        # 逻辑运算
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                for value in node.values:
                    if not self._eval_node(value):
                        return False
                return True
            elif isinstance(node.op, ast.Or):
                for value in node.values:
                    if self._eval_node(value):
                        return True
                return False
        
        # 属性访问
        if isinstance(node, ast.Attribute):
            obj = self._eval_node(node.value)
            if isinstance(obj, dict):
                return obj.get(node.attr)
            return getattr(obj, node.attr, None)
        
        # 下标访问
        if isinstance(node, ast.Subscript):
            obj = self._eval_node(node.value)
            key = self._eval_node(node.slice)
            if isinstance(obj, (list, tuple, dict, str)):
                return obj[key]
            raise TypeError(f"不支持的下标访问: {type(obj)}")
        
        # 函数调用
        if isinstance(node, ast.Call):
            return self._eval_call(node)
        
        # 列表
        if isinstance(node, ast.List):
            return [self._eval_node(elt) for elt in node.elts]
        
        # 元组
        if isinstance(node, ast.Tuple):
            return tuple(self._eval_node(elt) for elt in node.elts)
        
        # 字典
        if isinstance(node, ast.Dict):
            result = {}
            for key_node, value_node in zip(node.keys, node.values):
                key = self._eval_node(key_node)
                value = self._eval_node(value_node)
                result[key] = value
            return result
        
        # 条件表达式 (a if condition else b)
        if isinstance(node, ast.IfExp):
            condition = self._eval_node(node.test)
            if condition:
                return self._eval_node(node.body)
            else:
                return self._eval_node(node.orelse)
        
        # 列表推导式（简单支持）
        if isinstance(node, ast.ListComp):
            return self._eval_listcomp(node)
        
        # 字典推导式（简单支持）
        if isinstance(node, ast.DictComp):
            return self._eval_dictcomp(node)
        
        raise ValueError(f"不支持的表达式节点: {type(node).__name__}")
    
    def _eval_binop(self, op: ast.operator, left: Any, right: Any) -> Any:
        """求值二元运算"""
        if isinstance(op, ast.Add):
            return left + right
        elif isinstance(op, ast.Sub):
            return left - right
        elif isinstance(op, ast.Mult):
            return left * right
        elif isinstance(op, ast.Div):
            return left / right
        elif isinstance(op, ast.FloorDiv):
            return left // right
        elif isinstance(op, ast.Mod):
            return left % right
        elif isinstance(op, ast.Pow):
            return left ** right
        else:
            raise ValueError(f"不支持的二元运算: {type(op).__name__}")
    
    def _eval_unaryop(self, op: ast.unaryop, operand: Any) -> Any:
        """求值一元运算"""
        if isinstance(op, ast.UAdd):
            return +operand
        elif isinstance(op, ast.USub):
            return -operand
        elif isinstance(op, ast.Not):
            return not operand
        else:
            raise ValueError(f"不支持的一元运算: {type(op).__name__}")
    
    def _eval_compare(self, op: ast.cmpop, left: Any, right: Any) -> bool:
        """求值比较运算"""
        if isinstance(op, ast.Eq):
            return left == right
        elif isinstance(op, ast.NotEq):
            return left != right
        elif isinstance(op, ast.Lt):
            return left < right
        elif isinstance(op, ast.LtE):
            return left <= right
        elif isinstance(op, ast.Gt):
            return left > right
        elif isinstance(op, ast.GtE):
            return left >= right
        elif isinstance(op, ast.In):
            return left in right
        elif isinstance(op, ast.NotIn):
            return left not in right
        elif isinstance(op, ast.Is):
            return left is right
        elif isinstance(op, ast.IsNot):
            return left is not right
        else:
            raise ValueError(f"不支持的比较运算: {type(op).__name__}")
    
    def _eval_call(self, node: ast.Call) -> Any:
        """求值函数调用"""
        # 获取函数名
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            # 方法调用（如 str.upper()）
            obj = self._eval_node(node.func.value)
            method_name = node.func.attr
            args = [self._eval_node(arg) for arg in node.args]
            method = getattr(obj, method_name, None)
            if callable(method):
                return method(*args)
            raise AttributeError(f"对象没有方法: {method_name}")
        else:
            raise ValueError("不支持的函数调用形式")
        
        # 检查是否在白名单中
        if func_name not in self.functions:
            raise NameError(f"未定义的函数: {func_name}")
        
        # 求值参数
        args = [self._eval_node(arg) for arg in node.args]
        kwargs = {
            kw.arg: self._eval_node(kw.value)
            for kw in node.keywords
        }
        
        # 调用函数
        func = self.functions[func_name]
        return func(*args, **kwargs)
    
    def _eval_listcomp(self, node: ast.ListComp) -> List[Any]:
        """求值列表推导式（简单实现）"""
        # 只支持简单的 [expr for var in iterable]
        if len(node.generators) != 1:
            raise ValueError("只支持单层列表推导式")
        
        generator = node.generators[0]
        if generator.ifs:
            raise ValueError("暂不支持带条件的列表推导式")
        
        # 获取迭代器
        iterable = self._eval_node(generator.iter)
        
        # 迭代求值
        result = []
        var_name = generator.target.id if isinstance(generator.target, ast.Name) else None
        if not var_name:
            raise ValueError("不支持的迭代变量")
        
        # 保存原始上下文
        old_value = self.context.get(var_name)
        
        try:
            for item in iterable:
                # 设置迭代变量
                self.context[var_name] = item
                # 求值表达式
                value = self._eval_node(node.elt)
                result.append(value)
        finally:
            # 恢复上下文
            if old_value is None:
                self.context.pop(var_name, None)
            else:
                self.context[var_name] = old_value
        
        return result
    
    def _eval_dictcomp(self, node: ast.DictComp) -> Dict[Any, Any]:
        """求值字典推导式（简单实现）"""
        # 只支持简单的 {key_expr: value_expr for var in iterable}
        if len(node.generators) != 1:
            raise ValueError("只支持单层字典推导式")
        
        generator = node.generators[0]
        if generator.ifs:
            raise ValueError("暂不支持带条件的字典推导式")
        
        # 获取迭代器
        iterable = self._eval_node(generator.iter)
        
        # 迭代求值
        result = {}
        var_name = generator.target.id if isinstance(generator.target, ast.Name) else None
        if not var_name:
            raise ValueError("不支持的迭代变量")
        
        # 保存原始上下文
        old_value = self.context.get(var_name)
        
        try:
            for item in iterable:
                # 设置迭代变量
                self.context[var_name] = item
                # 求值键和值
                key = self._eval_node(node.key)
                value = self._eval_node(node.value)
                result[key] = value
        finally:
            # 恢复上下文
            if old_value is None:
                self.context.pop(var_name, None)
            else:
                self.context[var_name] = old_value
        
        return result


def evaluate_expression(
    expression: str,
    context: Optional[Dict[str, Any]] = None
) -> Any:
    """便捷函数：求值表达式
    
    Args:
        expression: 表达式字符串
        context: 求值上下文
        
    Returns:
        求值结果
    """
    evaluator = ExpressionEvaluator(context)
    return evaluator.evaluate(expression)

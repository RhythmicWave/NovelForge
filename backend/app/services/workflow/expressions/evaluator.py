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
                # and: 返回第一个假值，或最后一个值
                result = True
                for value_node in node.values:
                    result = self._eval_node(value_node)
                    if not result:
                        return result
                return result
            elif isinstance(node.op, ast.Or):
                # or: 返回第一个真值，或最后一个值
                result = False
                for value_node in node.values:
                    result = self._eval_node(value_node)
                    if result:
                        return result
                return result
        
        # 属性访问
        if isinstance(node, ast.Attribute):
            obj = self._eval_node(node.value)
            if isinstance(obj, dict):
                # 字典：使用 get 方法，不存在返回 None
                return obj.get(node.attr)
            elif obj is None:
                # 如果对象是 None，返回 None（支持链式访问）
                return None
            else:
                # 其他对象：使用 getattr，不存在返回 None
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
                if key_node is None:
                    # 字典解包：{**dict1, **dict2}
                    # key 为 None 表示这是一个解包操作
                    dict_to_unpack = self._eval_node(value_node)
                    if isinstance(dict_to_unpack, dict):
                        result.update(dict_to_unpack)
                    else:
                        raise TypeError(f"只能解包字典类型，当前类型: {type(dict_to_unpack)}")
                else:
                    # 普通键值对
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
        
        # f-string（格式化字符串字面量）
        if isinstance(node, ast.JoinedStr):
            return self._eval_joinedstr(node)
        
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
            # 方法调用（如 str.upper()、dict.get()）
            obj = self._eval_node(node.func.value)
            method_name = node.func.attr
            args = [self._eval_node(arg) for arg in node.args]
            kwargs = {
                kw.arg: self._eval_node(kw.value)
                for kw in node.keywords
            }
            
            # 特殊处理：如果对象有 model_dump 方法（Pydantic 模型），先转换为字典
            if hasattr(obj, 'model_dump') and method_name == 'get':
                obj = obj.model_dump()
            elif hasattr(obj, 'dict') and method_name == 'get':
                obj = obj.dict()
            
            # 获取方法
            method = getattr(obj, method_name, None)
            if callable(method):
                return method(*args, **kwargs)
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

        # 处理迭代变量（可能是元组解包）
        target = generator.target
        if isinstance(target, ast.Name):
            # 简单变量：for var in ...
            var_names = [target.id]
        elif isinstance(target, (ast.Tuple, ast.List)):
            # 元组解包：for i, val in ...
            var_names = [elt.id for elt in target.elts if isinstance(elt, ast.Name)]
        else:
            raise ValueError("不支持的迭代变量")

        # 保存原始上下文
        old_values = {name: self.context.get(name) for name in var_names}

        try:
            for item in iterable:
                # 设置迭代变量
                if len(var_names) == 1:
                    # 简单赋值
                    self.context[var_names[0]] = item
                else:
                    # 元组解包
                    if not isinstance(item, (tuple, list)) or len(item) != len(var_names):
                        raise ValueError(f"无法解包迭代项: {item}")
                    for name, value in zip(var_names, item):
                        self.context[name] = value

                # 求值表达式
                value = self._eval_node(node.elt)
                result.append(value)
        finally:
            # 恢复上下文
            for name in var_names:
                if old_values[name] is None:
                    self.context.pop(name, None)
                else:
                    self.context[name] = old_values[name]

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

        # 处理迭代变量（可能是元组解包）
        target = generator.target
        if isinstance(target, ast.Name):
            # 简单变量：for var in ...
            var_names = [target.id]
        elif isinstance(target, (ast.Tuple, ast.List)):
            # 元组解包：for i, val in ...
            var_names = [elt.id for elt in target.elts if isinstance(elt, ast.Name)]
        else:
            raise ValueError("不支持的迭代变量")

        # 保存原始上下文
        old_values = {name: self.context.get(name) for name in var_names}

        try:
            for item in iterable:
                # 设置迭代变量
                if len(var_names) == 1:
                    # 简单赋值
                    self.context[var_names[0]] = item
                else:
                    # 元组解包
                    if not isinstance(item, (tuple, list)) or len(item) != len(var_names):
                        raise ValueError(f"无法解包迭代项: {item}")
                    for name, value in zip(var_names, item):
                        self.context[name] = value

                # 求值键和值
                key = self._eval_node(node.key)
                value = self._eval_node(node.value)
                result[key] = value
        finally:
            # 恢复上下文
            for name in var_names:
                if old_values[name] is None:
                    self.context.pop(name, None)
                else:
                    self.context[name] = old_values[name]

        return result
    
    def _eval_joinedstr(self, node: ast.JoinedStr) -> str:
        """求值 f-string（格式化字符串字面量）
        
        f-string 在 AST 中表示为 JoinedStr 节点，包含多个部分：
        - Constant: 普通字符串部分
        - FormattedValue: 格式化表达式部分（{expr}）
        
        例如：f"Hello {name}!" 
        → JoinedStr([Constant("Hello "), FormattedValue(Name("name")), Constant("!")])
        """
        parts = []
        
        for value in node.values:
            if isinstance(value, ast.Constant):
                # 普通字符串部分
                parts.append(str(value.value))
            elif isinstance(value, ast.FormattedValue):
                # 格式化表达式部分
                expr_value = self._eval_node(value.value)
                
                # 处理格式说明符（如果有）
                if value.format_spec:
                    # format_spec 也是一个 JoinedStr
                    format_spec = self._eval_joinedstr(value.format_spec)
                    parts.append(format(expr_value, format_spec))
                else:
                    # 没有格式说明符，直接转字符串
                    parts.append(str(expr_value))
            else:
                raise ValueError(f"f-string 中不支持的节点类型: {type(value).__name__}")
        
        return ''.join(parts)


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

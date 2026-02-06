"""XML 格式工作流解析器

新的工作流 DSL 格式，使用 XML 标签明确标记节点边界。

语法示例：
    <node name="trigger">
      trigger = Trigger.Manual()
    </node>
    
    <node name="cards" async="true" disabled="false">
      cards = Card.BatchUpsert(...)
    </node>
"""

import re
import ast
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Tuple, Set
from loguru import logger

from ..engine.execution_plan import Statement, ExecutionPlan


class XMLWorkflowParser:
    """XML 格式工作流解析器"""
    
    def parse(self, code: str) -> ExecutionPlan:
        """解析工作流代码
        
        Args:
            code: XML 格式的工作流代码（支持 # 注释和 <!-- --> 注释）
            
        Returns:
            ExecutionPlan 对象
            
        Raises:
            ValueError: 语法错误或验证失败
        """
        if not code or not code.strip():
            return ExecutionPlan(statements=[], dependencies={})
        
        # 预处理：将 # 注释转换为 XML 注释
        code = self._preprocess_comments(code)
        
        # 包装成合法的 XML 文档
        xml_code = f"<workflow>\n{code}\n</workflow>"
        
        try:
            root = ET.fromstring(xml_code)
        except ET.ParseError as e:
            raise ValueError(f"工作流语法错误: {e}")
        
        statements = []
        line_number = 1
        
        for node_elem in root.findall('node'):
            try:
                stmt = self._parse_node_element(node_elem, line_number)
                statements.append(stmt)
                line_number += 1
            except Exception as e:
                node_name = node_elem.get('name', '未知')
                raise ValueError(f"解析节点 '{node_name}' 失败: {e}")
        
        # 构建依赖关系
        dependencies = {
            stmt.variable: stmt.depends_on
            for stmt in statements
        }
        
        plan = ExecutionPlan(
            statements=statements,
            dependencies=dependencies
        )
        
        # 验证执行计划
        plan.validate()
        
        logger.debug(f"[XMLParser] 解析成功，共 {len(statements)} 个节点")
        return plan
    
    def _preprocess_comments(self, code: str) -> str:
        """预处理注释：将 # 注释转换为 XML 注释
        
        Args:
            code: 原始代码
            
        Returns:
            处理后的代码
        """
        lines = code.split('\n')
        processed_lines = []
        
        for line in lines:
            stripped = line.strip()
            
            # 如果是 # 注释（不在节点内部）
            if stripped.startswith('#') and '<node' not in line and '</node>' not in line:
                # 转换为 XML 注释
                comment_text = stripped[1:].strip()
                if comment_text:
                    processed_lines.append(f'<!-- {comment_text} -->')
                else:
                    processed_lines.append('')
            else:
                # 保持原样
                processed_lines.append(line)
        
        return '\n'.join(processed_lines)
    
    def _parse_node_element(self, node_elem: ET.Element, line_number: int) -> Statement:
        """解析单个节点元素
        
        Args:
            node_elem: XML 节点元素
            line_number: 行号
            
        Returns:
            Statement 对象
        """
        # 1. 提取属性
        name = node_elem.get('name')
        if not name:
            raise ValueError("节点缺少 name 属性")
        
        # 解析 disabled 属性（默认 false）
        disabled_str = node_elem.get('disabled', 'false').lower()
        disabled = disabled_str in ('true', '1', 'yes')
        
        # 解析 async 属性（默认 false）
        async_str = node_elem.get('async', 'false').lower()
        is_async = async_str in ('true', '1', 'yes')
        
        # 2. 提取节点代码（只包含调用表达式，不包含变量赋值）
        call_expr = (node_elem.text or '').strip()
        if not call_expr:
            raise ValueError(f"节点 '{name}' 没有代码")
        
        # 3. 解析节点调用：NodeType.Method(...)
        node_type, config = self._parse_node_call(call_expr)
        
        # 4. 提取依赖
        depends_on = self._extract_dependencies(call_expr, node_type)
        
        # 5. 创建 Statement（使用 name 作为变量名）
        stmt = Statement(
            line_number=line_number,
            variable=name,
            node_type=node_type,
            config=config,
            is_async=is_async,
            depends_on=depends_on,
            code=call_expr,  # 只存储调用表达式
            disabled=disabled
        )
        
        logger.debug(
            f"[XMLParser] 节点: {name}, 类型: {node_type}, "
            f"async: {is_async}, disabled: {disabled}"
        )
        
        return stmt
    
    def _parse_node_call(self, call_expr: str) -> Tuple[str, Dict[str, Any]]:
        """解析节点调用表达式
        
        Args:
            call_expr: 节点调用表达式，如 "Card.Read(card_id=123)"
            
        Returns:
            (node_type, config) 元组
            
        Raises:
            ValueError: 解析失败
        """
        try:
            # 解析为 AST
            expr = ast.parse(call_expr, mode='eval').body
            
            if not isinstance(expr, ast.Call):
                raise ValueError("不是有效的节点调用")
            
            # 提取节点类型：NodeType.Method
            if isinstance(expr.func, ast.Attribute):
                # NodeType.Method 格式
                if isinstance(expr.func.value, ast.Name):
                    category = expr.func.value.id
                    method = expr.func.attr
                    node_type = f"{category}.{method}"
                elif isinstance(expr.func.value, ast.Attribute):
                    # 支持多级：A.B.C
                    parts = []
                    node = expr.func
                    while isinstance(node, ast.Attribute):
                        parts.insert(0, node.attr)
                        node = node.value
                    if isinstance(node, ast.Name):
                        parts.insert(0, node.id)
                    node_type = '.'.join(parts)
                else:
                    raise ValueError("不支持的节点类型格式")
            else:
                raise ValueError("节点调用必须是 NodeType.Method(...) 格式")
            
            # 提取参数
            config = {}
            for keyword in expr.keywords:
                key = keyword.arg
                # 解析参数值（保持类型或标记为变量引用）
                value = self._parse_value(keyword.value)
                config[key] = value
            
            return node_type, config
            
        except SyntaxError as e:
            raise ValueError(f"语法错误: {e}")
        except Exception as e:
            raise ValueError(f"解析失败: {e}")
    
    def _parse_value(self, node: ast.AST) -> Any:
        """解析参数值
        
        支持：
        1. 常量：字符串、数字、布尔值（保持原始类型）
        2. 变量引用：trigger.project_id（标记为 $trigger.project_id）
        3. 列表/字典字面量（保持原始类型）
        4. 表达式：标记为 ${expression}
        """
        if isinstance(node, ast.Constant):
            # 保持原始类型：字符串、数字、布尔值、None
            return node.value
        
        elif isinstance(node, ast.Name):
            # 变量引用
            return f"${node.id}"
        
        elif isinstance(node, ast.Attribute):
            # 属性访问：trigger.project_id
            obj = self._parse_value(node.value)
            return f"{obj}.{node.attr}"
        
        elif isinstance(node, ast.List):
            # 列表字面量 - 保持为真正的列表
            return [self._parse_value(elt) for elt in node.elts]
        
        elif isinstance(node, ast.Dict):
            # 字典字面量 - 保持为真正的字典
            return {
                self._parse_value(k): self._parse_value(v)
                for k, v in zip(node.keys, node.values)
            }
        
        elif isinstance(node, (ast.ListComp, ast.DictComp)):
            # 列表/字典推导式 - 保存为表达式字符串
            return f"${{{ast.unparse(node)}}}"
        
        else:
            # 其他表达式 - 保存为字符串
            return f"${{{ast.unparse(node)}}}"
    
    def _extract_dependencies(self, expr: str, exclude_node_type: str = None) -> List[str]:
        """提取表达式中的变量依赖
        
        Args:
            expr: 表达式字符串
            exclude_node_type: 要排除的节点类型（如 "Card.Read"）
            
        Returns:
            依赖的变量名列表
        """
        try:
            tree = ast.parse(expr, mode='eval')
        except:
            return []
        
        dependencies = set()
        
        # 提取节点类型的各个部分（用于排除）
        exclude_parts = set()
        if exclude_node_type:
            exclude_parts = set(exclude_node_type.split('.'))
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                # 排除内置名称和节点类型
                if node.id not in ['True', 'False', 'None'] and node.id not in exclude_parts:
                    dependencies.add(node.id)
            elif isinstance(node, ast.Attribute):
                # 提取属性访问的根变量：a.b.c -> a
                root = node
                while isinstance(root, ast.Attribute):
                    root = root.value
                if isinstance(root, ast.Name):
                    if root.id not in exclude_parts:
                        dependencies.add(root.id)
        
        return sorted(list(dependencies))


def parse_workflow(code: str) -> ExecutionPlan:
    """便捷函数：解析工作流代码
    
    Args:
        code: XML 格式的工作流代码
        
    Returns:
        ExecutionPlan 对象
    """
    parser = XMLWorkflowParser()
    return parser.parse(code)

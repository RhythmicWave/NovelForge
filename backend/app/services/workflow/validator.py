"""工作流代码校验器

在工作流保存时进行静态检查，提前发现错误。
"""

from typing import List, Dict, Any, Optional, Iterable, Tuple
from dataclasses import dataclass
from loguru import logger

from .registry import NodeRegistry
from .expressions import validate_expression
from .expressions.evaluator import get_expression_dependencies


@dataclass
class ValidationError:
    """校验错误"""
    line: int
    variable: str
    error_type: str  # 'syntax', 'node_type', 'field_access', 'expression', 'type_mismatch'
    message: str
    suggestion: Optional[str] = None


@dataclass
class ValidationResult:
    """校验结果"""
    is_valid: bool
    errors: List[ValidationError]
    warnings: List[ValidationError]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'is_valid': self.is_valid,
            'errors': [
                {
                    'line': e.line,
                    'variable': e.variable,
                    'error_type': e.error_type,
                    'message': e.message,
                    'suggestion': e.suggestion
                }
                for e in self.errors
            ],
            'warnings': [
                {
                    'line': w.line,
                    'variable': w.variable,
                    'error_type': w.error_type,
                    'message': w.message,
                    'suggestion': w.suggestion
                }
                for w in self.warnings
            ]
        }


class WorkflowValidator:
    """工作流校验器"""
    
    def __init__(self):
        self.registry = NodeRegistry()
        self.errors: List[ValidationError] = []
        self.warnings: List[ValidationError] = []
    
    def validate(self, code: str) -> ValidationResult:
        """校验工作流代码
        
        Args:
            code: 工作流 DSL 代码（注释标记 DSL）
            
        Returns:
            校验结果
        """
        self.errors = []
        self.warnings = []
        
        try:
            # 解析代码
            from .parser.marker_parser import WorkflowParser
            parser = WorkflowParser()
            
            # 1. 解析代码（会检查语法错误）
            plan = parser.parse(code)
            
            # 2. 检查节点类型
            self._validate_node_types(plan.statements)
            
            # 3. 检查字段访问
            self._validate_field_access(plan.statements)
            
            # 4. 检查表达式语法
            self._validate_expressions(plan.statements)
            
            # 5. 检查类型匹配
            self._validate_type_matching(plan.statements)
            
            # 6. 检查 Expression 节点特殊规则
            self._validate_expression_nodes(plan.statements)
            
            # 7. 检查异步依赖
            self._validate_async_dependencies(plan.statements)
            
            # 8. 检查参数值的有效性
            self._validate_parameter_values(plan.statements)
            
        except SyntaxError as e:
            self.errors.append(ValidationError(
                line=e.lineno or 0,
                variable='',
                error_type='syntax',
                message=f"语法错误: {str(e)}",
                suggestion="检查代码语法是否正确"
            ))
        except ValueError as e:
            # 解析器抛出的错误
            self.errors.append(ValidationError(
                line=0,
                variable='',
                error_type='syntax',
                message=str(e),
                suggestion="检查代码是否符合 DSL 规范"
            ))
        except Exception as e:
            logger.error(f"校验失败: {e}")
            self.errors.append(ValidationError(
                line=0,
                variable='',
                error_type='unknown',
                message=f"校验失败: {str(e)}",
                suggestion="请联系开发人员"
            ))
        
        return ValidationResult(
            is_valid=len(self.errors) == 0,
            errors=self.errors,
            warnings=self.warnings
        )
    
    def _validate_node_types(self, statements):
        """检查节点类型是否存在"""
        for stmt in statements:
            if stmt.node_type and not self.registry.has_node(stmt.node_type):
                self.errors.append(ValidationError(
                    line=stmt.line_number,
                    variable=stmt.variable,
                    error_type='node_type',
                    message=f"未知的节点类型: {stmt.node_type}",
                    suggestion=f"可用的节点类型: {', '.join(self.registry.list_nodes())}"
                ))
    
    def _validate_field_access(self, statements):
        """检查字段访问是否合法"""
        # 构建变量 -> 节点类型映射
        var_to_node_type = {}
        for stmt in statements:
            if stmt.node_type:
                var_to_node_type[stmt.variable] = stmt.node_type
        
        for stmt in statements:
            # 检查配置中的字段引用
            for key, value in stmt.config.items():
                if isinstance(value, str) and value.startswith('$'):
                    # 变量引用，如 $card.title
                    ref = value[1:]  # 去掉 $
                    self._check_field_reference(stmt, ref, var_to_node_type)
    
    def _check_field_reference(self, stmt, ref: str, var_to_node_type: Dict[str, str]):
        """检查字段引用是否合法"""
        parts = ref.split('.')
        if len(parts) < 2:
            return  # 简单变量引用，不检查
        
        var_name = parts[0]
        field_name = parts[1]
        
        # 检查变量是否存在
        if var_name not in var_to_node_type:
            self.errors.append(ValidationError(
                line=stmt.line_number,
                variable=stmt.variable,
                error_type='field_access',
                message=f"引用了未定义的变量: {var_name}",
                suggestion=f"确保在使用前定义变量 {var_name}"
            ))
            return
        
        # 获取节点类型
        node_type = var_to_node_type[var_name]
        node_class = self.registry.get(node_type)
        
        if not node_class or not hasattr(node_class, 'output_model'):
            return  # 无法检查
        
        # 检查字段是否存在
        output_schema = node_class.output_model.model_json_schema()
        if field_name not in output_schema.get('properties', {}):
            available_fields = list(output_schema.get('properties', {}).keys())
            self.errors.append(ValidationError(
                line=stmt.line_number,
                variable=stmt.variable,
                error_type='field_access',
                message=f"节点 {var_name} ({node_type}) 没有输出字段 '{field_name}'",
                suggestion=f"可用字段: {', '.join(available_fields)}"
            ))
    
    def _validate_expressions(self, statements):
        """检查表达式语法与变量依赖"""
        defined_vars = set()

        for stmt in statements:
            # 1) Logic.Expression 节点 expression 参数
            if stmt.node_type == "Logic.Expression":
                expression = stmt.config.get('expression', '')
                if expression:
                    self._validate_single_expression(
                        stmt=stmt,
                        expression=expression,
                        source="expression",
                        defined_vars=defined_vars
                    )

            # 2) 通用内联表达式：${...}
            for source, inline_expr in self._extract_inline_expressions(stmt.config):
                self._validate_single_expression(
                    stmt=stmt,
                    expression=inline_expr,
                    source=source,
                    defined_vars=defined_vars
                )

            # 当前节点定义的变量在本语句结束后可用
            defined_vars.add(stmt.variable)

    def _validate_single_expression(
        self,
        stmt,
        expression: str,
        source: str,
        defined_vars: set[str]
    ) -> None:
        """校验单个表达式"""
        expression_errors = validate_expression(expression)
        if expression_errors:
            for expression_error in expression_errors:
                self.errors.append(ValidationError(
                    line=stmt.line_number,
                    variable=stmt.variable,
                    error_type='expression',
                    message=f"表达式语法错误 ({source}): {expression_error}",
                    suggestion="检查表达式语法是否正确"
                ))
            return

        dependencies = get_expression_dependencies(expression)
        undefined_vars = sorted(var for var in dependencies if var not in defined_vars)
        if undefined_vars:
            defined_preview = ", ".join(sorted(defined_vars)) if defined_vars else "（当前无可用变量）"
            self.errors.append(ValidationError(
                line=stmt.line_number,
                variable=stmt.variable,
                error_type='expression',
                message=f"表达式引用了未定义变量 ({source}): {', '.join(undefined_vars)}",
                suggestion=f"请先定义这些变量，或检查变量名拼写。当前可用变量: {defined_preview}"
            ))

    def _extract_inline_expressions(
        self,
        value: Any,
        path: str = ""
    ) -> Iterable[Tuple[str, str]]:
        """递归提取配置中的内联表达式 ${...}"""
        if isinstance(value, str):
            if value.startswith("${") and value.endswith("}"):
                source = path if path else "config"
                yield source, value[2:-1]
            return

        if isinstance(value, list):
            for index, item in enumerate(value):
                child_path = f"{path}[{index}]" if path else f"[{index}]"
                yield from self._extract_inline_expressions(item, child_path)
            return

        if isinstance(value, dict):
            for key, item in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                yield from self._extract_inline_expressions(item, child_path)
    
    def _validate_type_matching(self, statements):
        """检查类型匹配"""
        # 构建变量 -> 输出类型映射
        var_to_output_type = {}
        
        for stmt in statements:
            if not stmt.node_type:
                continue
            
            node_class = self.registry.get(stmt.node_type)
            if not node_class:
                continue
            
            # 特殊处理：Expression 节点的输出类型是动态的
            if stmt.node_type == "Logic.Expression":
                var_to_output_type[stmt.variable] = 'any'
            elif hasattr(node_class, 'output_model'):
                var_to_output_type[stmt.variable] = node_class.output_model
        
        # 检查输入参数类型
        for stmt in statements:
            if not stmt.node_type:
                continue
            
            node_class = self.registry.get(stmt.node_type)
            if not node_class or not hasattr(node_class, 'input_model'):
                continue
            
            input_schema = node_class.input_model.model_json_schema()
            
            # 检查必填参数
            required_fields = input_schema.get('required', [])
            for field in required_fields:
                if field not in stmt.config:
                    self.errors.append(ValidationError(
                        line=stmt.line_number,
                        variable=stmt.variable,
                        error_type='type_mismatch',
                        message=f"缺少必填参数: {field}",
                        suggestion=f"节点 {stmt.node_type} 需要参数 {field}"
                    ))
            
            # 检查参数类型（简单检查）
            properties = input_schema.get('properties', {})
            for key, value in stmt.config.items():
                if key not in properties:
                    continue
                
                prop_schema = properties[key]
                expected_type = prop_schema.get('type')
                
                # 跳过变量引用和表达式
                # 变量引用格式：
                # 1. 直接变量：variable_name
                # 2. 属性访问：variable.field
                # 3. 模板字符串："{variable.field}"
                if isinstance(value, str):
                    # 检查是否是变量引用
                    is_variable_ref = (
                        # 包含点号（属性访问）
                        '.' in value or
                        # 包含花括号（模板字符串）
                        '{' in value or
                        # 是已知的变量名
                        value in [s.variable for s in statements]
                    )
                    
                    if is_variable_ref:
                        continue  # 跳过变量引用的类型检查
                
                # 简单类型检查（只检查字面量）
                if expected_type == 'array' and not isinstance(value, list):
                    self.errors.append(ValidationError(
                        line=stmt.line_number,
                        variable=stmt.variable,
                        error_type='type_mismatch',
                        message=f"参数 {key} 应该是列表类型，实际是 {type(value).__name__}",
                        suggestion=f"将 {key} 改为列表格式"
                    ))
                elif expected_type == 'object' and not isinstance(value, dict):
                    self.errors.append(ValidationError(
                        line=stmt.line_number,
                        variable=stmt.variable,
                        error_type='type_mismatch',
                        message=f"参数 {key} 应该是字典类型，实际是 {type(value).__name__}",
                        suggestion=f"将 {key} 改为字典格式"
                    ))
    
    def _validate_expression_nodes(self, statements):
        """检查 Expression 节点特殊规则"""
        for stmt in statements:
            if stmt.node_type != "Logic.Expression":
                continue
            
            expression = stmt.config.get('expression', '')
            if not expression:
                self.errors.append(ValidationError(
                    line=stmt.line_number,
                    variable=stmt.variable,
                    error_type='expression',
                    message="Expression 节点缺少 expression 参数",
                    suggestion="请填写表达式内容"
                ))
    
    def _validate_async_dependencies(self, statements):
        """检查异步节点依赖
        
        检查同步节点是否直接依赖异步节点的输出，而没有使用 wait 节点等待。
        """
        # 找出所有异步节点
        async_nodes = {stmt.variable for stmt in statements if stmt.is_async}
        
        if not async_nodes:
            return  # 没有异步节点，无需检查
        
        # 找出所有 wait 节点及其等待的异步节点
        # wait_node_name -> set of async_node_names
        wait_to_async = {}
        for stmt in statements:
            if stmt.node_type == "Logic.Wait":
                # Wait 节点的 tasks 参数可能是单个任务或任务列表
                tasks = stmt.config.get('tasks')
                waited = set()
                if tasks:
                    # 提取变量名（去掉 $ 前缀）
                    if isinstance(tasks, str):
                        task_var = tasks.lstrip('$')
                        if task_var in async_nodes:
                            waited.add(task_var)
                    elif isinstance(tasks, list):
                        for task in tasks:
                            if isinstance(task, str):
                                task_var = task.lstrip('$')
                                if task_var in async_nodes:
                                    waited.add(task_var)
                if waited:
                    wait_to_async[stmt.variable] = waited
        
        # 检查每个同步节点的依赖
        for stmt in statements:
            if stmt.is_async:
                continue  # 跳过异步节点
            
            if stmt.node_type == "Logic.Wait":
                continue  # 跳过 wait 节点本身
            
            # 收集所有依赖的变量（包括表达式中的）
            all_deps = set(stmt.depends_on)
            
            # 特别处理 Expression 节点：提取表达式中的变量
            if stmt.node_type == "Logic.Expression":
                expression = stmt.config.get('expression', '')
                if expression:
                    all_deps.update(get_expression_dependencies(expression))
            
            # 找出依赖的异步节点
            async_deps = all_deps & async_nodes
            
            if not async_deps:
                continue  # 没有依赖异步节点
            
            # 找出依赖的 wait 节点
            wait_deps = {dep for dep in all_deps if dep in wait_to_async}
            
            # 检查每个异步依赖是否有对应的 wait 节点
            for async_dep in async_deps:
                # 检查是否有 wait 节点等待这个异步节点
                has_wait = any(
                    async_dep in waited_async
                    for wait_node, waited_async in wait_to_async.items()
                    if wait_node in wait_deps
                )
                
                if not has_wait:
                    # 同步节点依赖了未等待的异步节点
                    self.errors.append(ValidationError(
                        line=stmt.line_number,
                        variable=stmt.variable,
                        error_type='async_dependency',
                        message=f"同步节点 '{stmt.variable}' 依赖异步节点 '{async_dep}'，但没有使用 wait 节点等待",
                        suggestion=(
                            f"在使用 '{async_dep}' 之前添加 wait 节点并在表达式中引用它，例如：\n"
                            f"#@node()\nwait_{async_dep} = Logic.Wait(tasks={async_dep})\n#</node>\n"
                            f"然后在表达式中引用 wait_{async_dep} 以确保等待完成"
                        )
                    ))
    
    def _validate_parameter_values(self, statements):
        """检查参数值的有效性
        
        检测常见的错误值，如：
        - '[object Object]': JavaScript 对象未正确序列化
        - 'undefined': JavaScript undefined 值
        - 'null' 字符串（应该是 None）
        """
        for stmt in statements:
            if not stmt.node_type:
                continue
            
            for key, value in stmt.config.items():
                # 检查字符串值
                if isinstance(value, str):
                    # 检测 [object Object]
                    if value == '[object Object]' or '[object Object]' in value:
                        self.errors.append(ValidationError(
                            line=stmt.line_number,
                            variable=stmt.variable,
                            error_type='invalid_value',
                            message=f"参数 '{key}' 的值无效: '{value}'",
                            suggestion="这通常是因为前端未正确序列化对象。请刷新页面或重新编辑该参数。"
                        ))
                    
                    # 检测 undefined
                    elif value == 'undefined':
                        self.errors.append(ValidationError(
                            line=stmt.line_number,
                            variable=stmt.variable,
                            error_type='invalid_value',
                            message=f"参数 '{key}' 的值为 undefined",
                            suggestion="请为该参数提供有效值或删除该参数。"
                        ))


def validate_workflow(code: str) -> ValidationResult:
    """便捷函数：校验工作流代码
    
    Args:
        code: 工作流代码
        
    Returns:
        校验结果
    """
    validator = WorkflowValidator()
    return validator.validate(code)

"""执行计划

表示工作流的执行计划，包含语句列表、依赖关系和并行组。
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Any


@dataclass
class Statement:
    """单条语句（一个节点调用或表达式）"""
    line_number: int
    variable: str              # 变量名
    node_type: Optional[str]   # 节点类型（如"Novel.Load"），None表示纯表达式
    config: Dict[str, Any]     # 节点配置
    is_async: bool             # 是否异步执行
    depends_on: List[str]      # 依赖的变量列表
    code: Optional[str] = None # 原始代码
    disabled: bool = False     # 是否禁用（从元数据注释中提取）

    def __repr__(self):
        return f"Statement(line={self.line_number}, var={self.variable}, type={self.node_type}, disabled={self.disabled})"


@dataclass
class ExecutionPlan:
    """执行计划"""
    statements: List[Statement]           # 语句列表（按代码顺序）
    dependencies: Dict[str, List[str]]    # 依赖关系：变量 → 依赖的变量列表

    def get_parallel_groups(self) -> List[List[Statement]]:
        """获取可并行执行的语句组

        设计原则：
        1. 默认顺序执行：每个语句一个组
        2. async 节点：标记为异步，但立即返回，不阻塞后续语句
        3. wait 语句：等待之前的异步节点完成

        返回：[[stmt1], [stmt2], [stmt3]]
        表示：按顺序执行每个语句
        """
        # 简化实现：每个语句一个组，顺序执行
        # async 和 wait 的处理在 AsyncExecutor 中实现
        groups = [[stmt] for stmt in self.statements]
        return groups

    def _can_merge_with_last_group(
        self,
        last_group: List[Statement],
        new_stmts: List[Statement]
    ) -> bool:
        """检查新语句是否可以与上一组并行执行

        条件：新语句不依赖上一组中的任何变量
        """
        last_group_vars = {stmt.variable for stmt in last_group}

        for new_stmt in new_stmts:
            # 如果新语句依赖上一组的变量，不能并行
            if any(dep in last_group_vars for dep in new_stmt.depends_on):
                return False

        return True

    def validate(self) -> None:
        """验证执行计划的正确性

        检查：
        1. 所有依赖的变量都有定义
        2. 没有循环依赖
        """
        defined_vars = set()

        for stmt in self.statements:
            # 检查依赖
            for dep in stmt.depends_on:
                if dep not in defined_vars:
                    raise ValueError(
                        f"行 {stmt.line_number}: 变量 '{stmt.variable}' "
                        f"依赖未定义的变量 '{dep}'"
                    )

            # 添加到已定义集合
            defined_vars.add(stmt.variable)

        # 尝试获取并行组（会检测循环依赖）
        try:
            self.get_parallel_groups()
        except ValueError as e:
            raise ValueError(f"执行计划验证失败: {e}")

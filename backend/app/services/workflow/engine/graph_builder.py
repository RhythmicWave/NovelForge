"""图构建器 - 解析DSL并构建执行图"""

from typing import Dict, List, Any, Set, Tuple
from loguru import logger

from ..types import ExecutionGraph


class GraphBuilder:
    """工作流图构建器
    
    职责：
    - 解析 JSON DSL
    - 构建有向无环图（DAG）
    - 验证图的合法性（循环检测、类型检查）
    - 计算拓扑排序
    - 识别可并发执行的节点
    """
    
    def build(self, definition: Dict[str, Any]) -> ExecutionGraph:
        """构建执行图
        
        Args:
            definition: 工作流定义（DSL）
            
        Returns:
            ExecutionGraph: 执行图
            
        Raises:
            ValueError: DSL格式错误或图不合法
        """
        nodes_list = definition.get("nodes", [])
        edges_list = definition.get("edges", [])
        
        if not nodes_list:
            raise ValueError("工作流至少需要一个节点")
        
        # 构建节点映射
        nodes = {node["id"]: node for node in nodes_list}
        
        # 构建依赖关系
        dependencies, successors = self._build_relationships(nodes, edges_list)
        
        # 找到起始节点
        start_nodes = self._find_start_nodes(nodes, dependencies)
        
        # 验证图的合法性
        self._validate_graph(nodes, dependencies, start_nodes)
        
        # 计算拓扑排序
        topology_order = self._topological_sort(nodes, dependencies, start_nodes)
        
        logger.info(
            f"[GraphBuilder] 图构建完成: {len(nodes)} 个节点, "
            f"{len(edges_list)} 条边, {len(start_nodes)} 个起始节点"
        )
        
        return ExecutionGraph(
            nodes=nodes,
            edges=edges_list,
            dependencies=dependencies,
            successors=successors,
            start_nodes=start_nodes,
            topology_order=topology_order
        )
    
    def _build_relationships(
        self, 
        nodes: Dict[str, Dict[str, Any]], 
        edges: List[Dict[str, Any]]
    ) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
        """构建依赖和后继关系
        
        从两个来源构建依赖：
        1. edges - 数据流边（实线）
        2. node.dependencies - 显式依赖声明（虚线）
        
        Returns:
            (dependencies, successors)
        """
        dependencies: Dict[str, List[str]] = {}
        successors: Dict[str, List[str]] = {}
        
        # 1. 从 edges 构建数据流依赖
        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            
            if not source or not target:
                logger.warning(f"[GraphBuilder] 边缺少source或target: {edge}")
                continue
            
            if source not in nodes:
                raise ValueError(f"边引用了不存在的源节点: {source}")
            if target not in nodes:
                raise ValueError(f"边引用了不存在的目标节点: {target}")
            
            # 记录依赖关系
            dependencies.setdefault(target, []).append(source)
            
            # 记录后继关系
            successors.setdefault(source, []).append(target)
        
        # 2. 从节点的 dependencies 字段构建显式依赖
        for node_id, node in nodes.items():
            node_deps = node.get("dependencies", [])
            if node_deps:
                # logger.info(f"[GraphBuilder] 节点 {node_id} 声明了显式依赖: {node_deps}")
                for dep_id in node_deps:
                    if dep_id not in nodes:
                        raise ValueError(f"节点 {node_id} 依赖了不存在的节点: {dep_id}")
                    
                    # 添加到依赖列表（去重）
                    if dep_id not in dependencies.get(node_id, []):
                        dependencies.setdefault(node_id, []).append(dep_id)
                    
                    # 添加到后继列表（去重）
                    if node_id not in successors.get(dep_id, []):
                        successors.setdefault(dep_id, []).append(node_id)
        
        return dependencies, successors
    
    def _find_start_nodes(
        self, 
        nodes: Dict[str, Dict[str, Any]], 
        dependencies: Dict[str, List[str]]
    ) -> List[str]:
        """找到起始节点（没有依赖的节点）"""
        start_nodes = [
            node_id for node_id in nodes.keys()
            if node_id not in dependencies or not dependencies[node_id]
        ]
        
        if not start_nodes:
            raise ValueError("工作流中没有起始节点，可能存在循环依赖")
        
        return start_nodes
    
    def _validate_graph(
        self,
        nodes: Dict[str, Dict[str, Any]],
        dependencies: Dict[str, List[str]],
        start_nodes: List[str]
    ) -> None:
        """验证图的合法性"""
        # 检测循环依赖
        self._detect_cycles(nodes, dependencies)
        
        # 检查是否所有节点都可达
        self._check_reachability(nodes, dependencies, start_nodes)
    
    def _detect_cycles(
        self,
        nodes: Dict[str, Dict[str, Any]],
        dependencies: Dict[str, List[str]]
    ) -> None:
        """检测循环依赖（使用DFS）"""
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {node_id: WHITE for node_id in nodes}
        
        def dfs(node_id: str, path: List[str]) -> None:
            if color[node_id] == GRAY:
                # 发现循环
                cycle = path[path.index(node_id):] + [node_id]
                raise ValueError(f"检测到循环依赖: {' -> '.join(cycle)}")
            
            if color[node_id] == BLACK:
                return
            
            color[node_id] = GRAY
            path.append(node_id)
            
            # 访问所有依赖（注意：这里是反向遍历）
            for dep in dependencies.get(node_id, []):
                dfs(dep, path[:])
            
            color[node_id] = BLACK
        
        for node_id in nodes:
            if color[node_id] == WHITE:
                dfs(node_id, [])
    
    def _check_reachability(
        self,
        nodes: Dict[str, Dict[str, Any]],
        dependencies: Dict[str, List[str]],
        start_nodes: List[str]
    ) -> None:
        """检查所有节点是否从起始节点可达"""
        # 构建后继关系用于正向遍历
        successors: Dict[str, List[str]] = {}
        for target, sources in dependencies.items():
            for source in sources:
                successors.setdefault(source, []).append(target)
        
        # BFS遍历
        visited: Set[str] = set()
        queue = list(start_nodes)
        
        while queue:
            node_id = queue.pop(0)
            if node_id in visited:
                continue
            
            visited.add(node_id)
            
            for successor in successors.get(node_id, []):
                if successor not in visited:
                    queue.append(successor)
        
        # 检查是否有孤立节点
        unreachable = set(nodes.keys()) - visited
        if unreachable:
            logger.warning(
                f"[GraphBuilder] 发现不可达节点（孤立节点）: {unreachable}"
            )
    
    def _topological_sort(
        self,
        nodes: Dict[str, Dict[str, Any]],
        dependencies: Dict[str, List[str]],
        start_nodes: List[str]
    ) -> List[str]:
        """拓扑排序（Kahn算法）
        
        返回节点的执行顺序，用于串行执行时的参考
        """
        # 计算入度
        in_degree = {node_id: len(dependencies.get(node_id, [])) for node_id in nodes}
        
        # 队列初始化为所有入度为0的节点
        queue = [node_id for node_id in start_nodes]
        result = []
        
        # 构建后继关系
        successors: Dict[str, List[str]] = {}
        for target, sources in dependencies.items():
            for source in sources:
                successors.setdefault(source, []).append(target)
        
        while queue:
            # 取出一个入度为0的节点
            node_id = queue.pop(0)
            result.append(node_id)
            
            # 将其所有后继节点的入度减1
            for successor in successors.get(node_id, []):
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    queue.append(successor)
        
        if len(result) != len(nodes):
            # 理论上不会到达这里，因为已经做了循环检测
            raise ValueError("拓扑排序失败，可能存在循环依赖")
        
        return result

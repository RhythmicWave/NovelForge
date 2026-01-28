"""节点基础工具函数"""

from typing import Any, Dict, Optional
from sqlmodel import Session, select

from app.db.models import Card, CardType
from ..types import ExecutionContext, ExecutionResult, NodePort

from pydantic import BaseModel, Field
from typing import ClassVar, List, Type, Dict


def get_card_by_id(session: Session, card_id: int) -> Optional[Card]:
    """根据ID获取卡片"""
    return session.get(Card, card_id)


def get_card_type_by_name(session: Session, type_name: str) -> Optional[CardType]:
    """根据名称获取卡片类型"""
    stmt = select(CardType).where(CardType.name == type_name)
    return session.exec(stmt).first()


def resolve_card_reference(
    session: Session,
    reference: Any,
    context_card_id: Optional[int] = None
) -> Optional[Card]:
    """解析卡片引用
    
    支持的引用格式：
    - 数字：直接作为卡片ID
    - "$self": 当前上下文卡片
    - "$parent": 父卡片
    - 字典 {"id": 123}: 显式指定ID
    
    Args:
        session: 数据库会话
        reference: 卡片引用
        context_card_id: 上下文卡片ID（用于$self等引用）
        
    Returns:
        Card对象，不存在则返回None
    """
    # 数字直接作为ID
    if isinstance(reference, int):
        return get_card_by_id(session, reference)
    
    # 字符串引用
    if isinstance(reference, str):
        if reference == "$self" and context_card_id:
            return get_card_by_id(session, context_card_id)
        elif reference == "$parent" and context_card_id:
            card = get_card_by_id(session, context_card_id)
            if card and card.parent_id:
                return get_card_by_id(session, card.parent_id)
    
    # 字典引用
    if isinstance(reference, dict):
        card_id = reference.get("id")
        if card_id:
            return get_card_by_id(session, card_id)
    
    return None


def format_string_template(template: str, data: Dict[str, Any]) -> str:
    """格式化字符串模板
    
    支持 {var} 和 {obj.field} 语法
    
    Args:
        template: 模板字符串
        data: 数据字典
        
    Returns:
        格式化后的字符串
    """
    import re
    
    def replace_var(match):
        var_path = match.group(1)
        parts = var_path.split('.')
        
        value = data
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                value = getattr(value, part, None)
            
            if value is None:
                return match.group(0)  # 保持原样
        
        return str(value)
    
    return re.sub(r'\{([^}]+)\}', replace_var, template)


# --- Class-Based Node Architecture (v2.0) ---

class BaseNodeConfig(BaseModel):
    """所有节点配置的基类 (v2.0)"""
    timeout: int = Field(60, description="超时时间(秒)")
    debug_mode: bool = Field(False, description="调试模式")
    
    class Config:
        arbitrary_types_allowed = True


class BaseNode:
    """工作流节点基类 (v2.0)"""
    
    # 元数据定义 (子类需覆盖)
    node_type: ClassVar[str]
    category: ClassVar[str]
    label: ClassVar[str]
    description: ClassVar[str] = ""
    
    # 配置模型 (子类需覆盖)
    config_model: ClassVar[Type[BaseModel]] = BaseNodeConfig

    def __init__(self, context: ExecutionContext):
        self.context = context

    @classmethod
    def get_ports(cls) -> Dict[str, List[NodePort]]:
        """定义节点的输入输出端口 (子类可覆盖)"""
        return {
            "inputs": getattr(cls, "inputs", []),
            "outputs": getattr(cls, "outputs", [])
        }

    @classmethod
    def extract_trigger_info(cls, config: Any) -> tuple[str | None, dict | None]:
        """提取触发器信息 (仅触发器节点需要实现)
        
        Returns:
            (card_type_name, filter_config)
            - card_type_name: 关联的卡片类型名称 (Project触发器传特定的魔术字符串)
            - filter_config: 过滤配置字典
            若返回 (None, None) 则表示非触发器或无配置
        """
        return None, None

    async def setup(self):
        """节点初始化 (如建立连接) - 可选"""
        pass

    async def execute(self, inputs: Dict[str, Any], config: BaseModel) -> ExecutionResult:
        """核心执行逻辑 - 必须实现"""
        raise NotImplementedError

    async def teardown(self):
        """资源释放 - 可选"""
        pass

    # --- Utility Wrappers for Convenience ---
    
    def resolve_card_reference(self, reference: Any) -> Optional[Card]:
        """解析卡片引用 (Wrapper)"""
        # 1. 尝试从 trigger 对象获取 (兼容旧逻辑)
        trigger = self.context.variables.get("trigger", {})
        context_card_id = trigger.get("card_id")
        
        # 2. 尝试从根作用域获取 (新逻辑: scope注入)
        if not context_card_id:
            context_card_id = self.context.variables.get("card_id")
            
        return resolve_card_reference(self.context.session, reference, context_card_id)

    def get_card_by_id(self, card_id: int) -> Optional[Card]:
        return get_card_by_id(self.context.session, card_id)


"""
工具调用结果的标准化类型定义

使用 Pydantic 定义工具返回值的结构，确保类型安全和字段清晰。
"""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ToolResultStatus(str, Enum):
    """工具执行状态枚举"""
    SUCCESS = "success"
    FAILED = "failed"
    WARNING = "warning"
    CONFIRMATION_REQUIRED = "confirmation_required"  # 需要用户确认


class ToolResult(BaseModel):
    """
    工具调用的标准返回格式
    
    所有助手工具都应该返回此格式或其子类，以确保返回值的一致性和可预测性。
    """
    success: bool = Field(description="操作是否成功")
    status: ToolResultStatus = Field(
        default=ToolResultStatus.SUCCESS,
        description="操作状态"
    )
    message: str = Field(description="给 LLM 的消息（简洁描述结果）")
    
    # 可选字段
    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="返回的数据（如卡片内容、列表等）"
    )
    error: Optional[str] = Field(
        default=None,
        description="错误信息（失败时提供详细错误）"
    )
    
    class Config:
        use_enum_values = True  # 序列化时使用枚举值


class ConfirmationRequest(ToolResult):
    """
    需要用户确认的操作请求
    
    当工具需要用户确认才能执行危险操作时，返回此类型。
    前端应检测此类型并展示确认对话框。
    """
    success: bool = False
    status: ToolResultStatus = ToolResultStatus.CONFIRMATION_REQUIRED
    
    confirmation_id: str = Field(description="确认请求的唯一ID")
    action: str = Field(description="要执行的操作名称（如 'delete_card'）")
    action_params: Dict[str, Any] = Field(description="操作的参数")
    warning: Optional[str] = Field(
        default=None,
        description="警告信息（如'此操作不可撤销'）"
    )
    
    class Config:
        use_enum_values = True


class CardOperationResult(ToolResult):
    """
    卡片操作的返回结果
    
    用于创建、更新、删除等卡片操作。
    """
    card_id: Optional[int] = Field(default=None, description="卡片ID")
    card_title: Optional[str] = Field(default=None, description="卡片标题")
    card_type: Optional[str] = Field(default=None, description="卡片类型")
    
    # AI 修改状态
    needs_confirmation: Optional[bool] = Field(
        default=None,
        description="是否需要用户确认（用于触发工作流）"
    )
    
    # 对于创建/更新操作
    current_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="卡片的当前数据"
    )
    missing_fields: Optional[List[str]] = Field(
        default=None,
        description="缺失的必填字段路径列表"
    )
    applied: Optional[int] = Field(
        default=None,
        description="成功执行的指令数"
    )
    failed: Optional[int] = Field(
        default=None,
        description="失败的指令数"
    )
    
    class Config:
        use_enum_values = True


class CardSearchResult(ToolResult):
    """卡片搜索结果"""
    total: int = Field(default=0, description="搜索到的卡片总数")
    cards: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="卡片列表"
    )
    
    class Config:
        use_enum_values = True


# 辅助函数：将 ToolResult 转换为 Dict
def to_dict(result: ToolResult) -> Dict[str, Any]:
    """
    将 ToolResult 对象转换为字典（用于 LangChain 工具返回）
    
    Args:
        result: ToolResult 对象
        
    Returns:
        字典格式的结果
    """
    return result.model_dump(exclude_none=True, mode='json')

"""业务异常定义

服务层抛出这些异常，API 层负责转换为 HTTP 响应。
"""


class BusinessException(Exception):
    """业务异常
    
    Args:
        message: 错误消息
        status_code: HTTP 状态码（404/400/409等）
    """
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)

# 为避免循环依赖，不在此处导入子模块。仅作为命名空间包保留。

# 导入 workflow 模块以触发装饰器注册（包括节点和触发器）
from . import workflow  # noqa: F401
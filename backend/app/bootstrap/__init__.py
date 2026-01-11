"""Bootstrap初始化模块

基于装饰器的插件化初始化系统。

## 架构设计

使用 @initializer 装饰器实现自动发现和注册：
- 每个初始化器独立成文件，通过装饰器声明
- 启动时自动扫描并按 order 顺序执行
- 新增初始化器无需修改任何现有代码

## 模块结构

- registry.py: 装饰器和自动发现机制
- prompts.py: 提示词初始化
- card_types.py: 卡片类型初始化
- knowledge.py: 知识库初始化  
- projects.py: 保留项目初始化
- workflows.py: 工作流初始化

## 使用方式

### 定义初始化器
```python
from .registry import initializer

@initializer(name="我的功能", order=60)
def init_my_feature(session: Session):
    logger.info("初始化我的功能...")
    # ... 初始化逻辑
```

### 自动执行所有初始化器
```python
from app.bootstrap.registry import discover_and_run_initializers

with Session(engine) as session:
    discover_and_run_initializers(session)
```

## 执行顺序

初始化器按 order 值从小到大执行：
- 10: 提示词
- 20: 卡片类型
- 30: 知识库
- 40: 保留项目
- 50: 工作流
- 60+: 自定义初始化器
"""

# 导出核心功能
from .registry import initializer, discover_and_run_initializers

# 导入所有初始化器模块以触发装饰器注册
from . import prompts
from . import card_types
from . import workflows
from . import knowledge

__all__ = [
    'initializer',
    'discover_and_run_initializers',
]

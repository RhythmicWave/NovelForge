# 所有 Data 节点已被删除
# 在代码式工作流中，这些功能可以用 Python 表达式替代：
# - Data.ExtractPath → 直接属性访问：novel.chapter_list
# - Data.Text → 字符串字面量："Hello World"
# - Data.Log → Python logger：logger.info(...)
# - Data.Reduce → Python reduce/sum：sum(numbers)
# - Data.GenerateRange → range + 列表推导：[{"index": i} for i in range(n)]
# - Data.Group → groupby/字典推导：{k: list(v) for k, v in groupby(...)}

__all__ = []

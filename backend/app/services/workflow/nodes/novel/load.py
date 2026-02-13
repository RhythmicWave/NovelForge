from typing import Any, Dict, List, Optional, AsyncIterator
import os
import re
from loguru import logger
from pydantic import Field, BaseModel

from ...registry import register_node
from ..base import BaseNode


class NovelLoadInput(BaseModel):
    """Novel.Load 节点输入 - 所有参数都在这里"""
    root_path: str = Field(
        ..., 
        description="小说根目录路径",
        json_schema_extra={"x-component": "DirectorySelect"}
    )
    file_pattern: str = Field(
        r".*\.(txt|md)$", 
        description="文件名匹配正则"
    )
    volume_pattern: str = Field(
        r"第[一二三四五六七八九十0-9]+[卷部纪]", 
        description="分卷文件夹匹配正则"
    )
    chapter_pattern: str = Field(
        r"第([零一二三四五六七八九十百千0-9]+)章", 
        description="章节名匹配正则（用于提取序号）"
    )


class NovelLoadOutput(BaseModel):
    """Novel.Load 节点输出"""
    chapter_list: List[Dict[str, Any]] = Field(..., description="章节元数据列表")
    volume_list: List[str] = Field(..., description="分卷列表")


@register_node
class NovelLoadNode(BaseNode[NovelLoadInput, NovelLoadOutput]):
    node_type = "Novel.Load"
    category = "novel"
    label = "加载小说"
    description = "扫描小说目录，生成章节列表元数据"
    
    input_model = NovelLoadInput
    output_model = NovelLoadOutput

    async def execute(self, inputs: NovelLoadInput) -> AsyncIterator[NovelLoadOutput]:
        """执行小说加载"""
        # 验证目录存在
        if not os.path.exists(inputs.root_path):
            raise ValueError(f"目录不存在: {inputs.root_path}")
            
        chapter_list = []
        volumes = set()
        
        # 编译正则
        try:
            file_re = re.compile(inputs.file_pattern)
            vol_re = re.compile(inputs.volume_pattern)
            chap_re = re.compile(inputs.chapter_pattern)
        except Exception as e:
            raise ValueError(f"正则编译失败: {e}")

        logger.info(f"[Novel.Load] 开始扫描: {inputs.root_path}")
        
        # 遍历目录
        for dirpath, dirnames, filenames in os.walk(inputs.root_path):
            # 确定当前分卷
            rel_path = os.path.relpath(dirpath, inputs.root_path)
            current_volume = "默认分卷"
            
            if rel_path != ".":
                parts = rel_path.split(os.sep)
                if parts:
                    potential_vol = parts[0]
                    if vol_re.search(potential_vol):
                        current_volume = potential_vol
                    else:
                        current_volume = potential_vol

            volumes.add(current_volume)
            
            for fname in filenames:
                if not file_re.match(fname):
                    continue
                    
                full_path = os.path.join(dirpath, fname)
                title = os.path.splitext(fname)[0]
                
                # 尝试提取章节序号
                idx = 0
                match = chap_re.search(title)
                if match:
                    if match.groups():
                        try:
                            idx = int(match.group(1))
                        except ValueError:
                            pass
                    else:
                        num_match = re.search(r"\d+", match.group())
                        if num_match:
                            idx = int(num_match.group())
                
                # 构建元数据
                meta = {
                    "title": title,
                    "path": full_path,
                    "volume": current_volume,
                    "index": idx,
                    "filename": fname
                }
                chapter_list.append(meta)

        # 排序
        chapter_list.sort(key=lambda x: (x['volume'], x['index'], x['title']))
        
        # 提取分卷列表并进行自然排序
        volumes_set = set(item['volume'] for item in chapter_list)
        
        # 自然排序函数
        def natural_sort_key(text):
            """将文本转换为可排序的键，支持中文数字和阿拉伯数字"""
            import re
            
            # 中文数字映射
            chinese_num_map = {
                '零': 0, '一': 1, '二': 2, '三': 3, '四': 4,
                '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
                '百': 100, '千': 1000
            }
            
            def chinese_to_num(s):
                """简单的中文数字转换（支持一到九十九）"""
                if not s:
                    return 0
                if s in chinese_num_map:
                    return chinese_num_map[s]
                # 处理 "十X" 或 "X十" 或 "X十X"
                if '十' in s:
                    parts = s.split('十')
                    if len(parts) == 2:
                        left = chinese_num_map.get(parts[0], 1 if not parts[0] else 0)
                        right = chinese_num_map.get(parts[1], 0)
                        return left * 10 + right
                return 0
            
            # 提取数字部分
            match = re.search(r'第([一二三四五六七八九十百千0-9]+)[卷部纪]', text)
            if match:
                num_str = match.group(1)
                # 尝试阿拉伯数字
                if num_str.isdigit():
                    return int(num_str)
                # 尝试中文数字
                return chinese_to_num(num_str)
            return 0
        
        volumes = sorted(list(volumes_set), key=natural_sort_key)
        
        logger.info(f"[Novel.Load] 扫描完成，共找到 {len(chapter_list)} 章节，{len(volumes)} 分卷")
        
        # 直接返回类型化的输出
        yield NovelLoadOutput(
            chapter_list=chapter_list,
            volume_list=volumes
        )

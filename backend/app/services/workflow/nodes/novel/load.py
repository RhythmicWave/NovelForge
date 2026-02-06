from typing import Any, Dict, List, Optional
import os
import re
from loguru import logger
from pydantic import Field

from ...registry import register_node
from ...types import ExecutionResult, NodePort
from ..base import BaseNode, BaseNodeConfig


class NovelLoadConfig(BaseNodeConfig):
    root_path: str = Field(..., description="小说根目录路径")
    file_pattern: str = Field(r".*\.(txt|md)$", description="文件名匹配正则")
    volume_pattern: str = Field(r"第[一二三四五六七八九十0-9]+[卷部纪]", description="分卷文件夹匹配正则")
    chapter_pattern: str = Field(r"第([零一二三四五六七八九十百千0-9]+)章", description="章节名匹配正则（用于提取序号）")


@register_node
class NovelLoadNode(BaseNode):
    node_type = "Novel.Load"
    category = "novel"
    label = "加载小说"
    description = "扫描小说目录，生成章节列表元数据"
    config_model = NovelLoadConfig

    @classmethod
    def get_ports(cls):
        return {
            "inputs": [
                NodePort("root_path", "string", required=False, description="根目录路径（覆盖配置）")
            ],
            "outputs": [
                NodePort("chapter_list", "list", description="章节元数据列表"),
                NodePort("volume_list", "list", description="分卷列表")
            ]
        }

    async def execute(self, inputs: Dict[str, Any], config: NovelLoadConfig) -> ExecutionResult:
        root_path = inputs.get("root_path") or config.root_path
        
        if not root_path or not os.path.exists(root_path):
            return ExecutionResult(success=False, error=f"目录不存在: {root_path}")
            
        chapter_list = []
        volumes = set()
        
        # 编译正则
        try:
            file_re = re.compile(config.file_pattern)
            vol_re = re.compile(config.volume_pattern)
            chap_re = re.compile(config.chapter_pattern)
        except Exception as e:
            return ExecutionResult(success=False, error=f"正则编译失败: {e}")

        logger.info(f"[Novel.Load] 开始扫描: {root_path}")
        
        # Walk directory
        for dirpath, dirnames, filenames in os.walk(root_path):
            # 确定当前分卷
            rel_path = os.path.relpath(dirpath, root_path)
            current_volume = "默认分卷"
            
            # 简单的分卷识别逻辑：检查路径中是否包含分卷名
            # 如果路径是 ".", 则是根目录
            if rel_path != ".":
                # 取路径的第一级作为分卷名 (假设结构是 root/volume/chapter.txt)
                parts = rel_path.split(os.sep)
                if parts:
                    potential_vol = parts[0]
                    if vol_re.search(potential_vol):
                        current_volume = potential_vol
                    else:
                        # 如果不像分卷，也暂时作为分卷名（或者层级名）
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
                    # 优先尝试捕获组
                    if match.groups():
                        try:
                            idx = int(match.group(1))
                        except ValueError:
                            pass
                    else:
                        # Fallback: 提取匹配串里的数字
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

        # 排序：先按分卷，再按index，最后按文件名
        # 简单的排序逻辑，可能无法完美处理中文数字
        chapter_list.sort(key=lambda x: (x['volume'], x['index'], x['title']))
        
        # 仅从实际找到的章节中提取分卷列表，避免空的"默认分卷"
        volumes = sorted(list(set(item['volume'] for item in chapter_list)))
        
        logger.info(f"[Novel.Load] 扫描完成，共找到 {len(chapter_list)} 章节，{len(volumes)} 分卷")
        
        return ExecutionResult(
            success=True,
            outputs={
                "chapter_list": chapter_list,
                "volume_list": volumes
            }
        )

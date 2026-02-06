"""指令流生成服务

负责调用 LLM 生成指令流，并进行实时校验和自动修复。
"""

import json
import re
import asyncio
from typing import AsyncIterator, Dict, Any, List, Optional
from sqlmodel import Session
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from pydantic import ValidationError
from loguru import logger

from app.services.ai.core.llm_service import build_chat_model
from app.services.ai.core.model_builder import build_model_from_json_schema
from app.services.ai.generation.instruction_validator import (
    validate_instruction, 
    apply_instruction,
    format_validation_errors
)
from app.services.ai.generation.prompt_builder import build_user_task_prompt
from app.schemas.instruction import ConversationMessage


async def generate_instruction_stream(
    session: Session,
    llm_config_id: int,
    user_prompt: str,
    system_prompt: str,
    schema: Dict[str, Any],
    current_data: Dict[str, Any],
    conversation_context: List[ConversationMessage],
    context_info: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    timeout: float = 150,
    max_retry: int = 3
) -> AsyncIterator[Dict[str, Any]]:
    """生成指令流（带自动校验与修复）
    
    Args:
        session: 数据库会话
        llm_config_id: LLM 配置 ID
        user_prompt: 用户输入的提示词
        system_prompt: 系统提示词
        schema: 目标数据结构的 JSON Schema
        current_data: 当前已生成的数据
        conversation_context: 对话历史
        temperature: 采样温度
        max_tokens: 最大生成 token 数
        timeout: 超时时间
        max_retry: 最大重试次数
        
    Yields:
        事件字典，包含 type 和对应的数据
    """
    # 构建 ChatModel
    try:
        chat_model = build_chat_model(
            session=session,
            llm_config_id=llm_config_id,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout
        )
    except Exception as e:
        logger.error(f"构建 ChatModel 失败: {e}")
        yield {
            "type": "error",
            "text": f"初始化 LLM 失败: {str(e)}"
        }
        return
    
    # 创建 Pydantic 动态模型（用于最终验证）
    try:
        DynamicModel = build_model_from_json_schema('DynamicResponseModel', schema)
    except Exception as e:
        logger.error(f"创建动态模型失败: {e}")
        yield {
            "type": "error",
            "text": f"Schema 解析失败: {str(e)}"
        }
        return
    
    # 收集已生成的数据（深拷贝避免修改原始数据）
    collected_data = dict(current_data)
    
    # 构建消息历史
    messages: List[BaseMessage] = [SystemMessage(content=system_prompt)]
    
    # 如果是首次生成（conversation_context为空），构建第一条用户消息
    if not conversation_context:
        # 构建第一条用户消息：上下文 + 用户要求 + 已有数据
        # （任务说明和 Schema 已经在 System Prompt 中）
        task_prompt = build_user_task_prompt(
            user_prompt=user_prompt or "请开始生成卡片内容",
            context_info=context_info,
            current_data=collected_data if collected_data else None
        )
        messages.append(HumanMessage(content=task_prompt))
    else:
        # 继续生成：添加历史对话上下文
        for msg in conversation_context:
            if msg.role == "user":
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                messages.append(AIMessage(content=msg.content))
        
        # 始终在最后添加已生成数据信息（如果有）
        # 这样 LLM 能够知道当前状态，避免重复生成
        if collected_data:
            current_data_info = f"\n\n## 当前已生成的数据\n\n```json\n{json.dumps(collected_data, ensure_ascii=False, indent=2)}\n```\n\n请继续生成缺失的字段，不要重复生成已有字段。"
            
            # 如果最后一条是用户消息，追加到该消息
            if messages and isinstance(messages[-1], HumanMessage):
                messages[-1].content += current_data_info
            else:
                # 否则新建一条用户消息
                messages.append(HumanMessage(content=current_data_info))
    
    # 打印完整的消息上下文（用于调试）
    logger.info("=" * 80)
    logger.info(f"[指令生成] 开始生成，共 {len(messages)} 条消息")
    for idx, msg in enumerate(messages):
        msg_type = type(msg).__name__
        content_preview = msg.content
        logger.info(f"  [{idx}] {msg_type}: {content_preview}")
    logger.info("=" * 80)
    
    # 开始生成循环（支持自动修复）
    failed_instructions = []  # 累积失败的指令
    generation_completed = False  # 标记是否正常完成
    
    for attempt in range(max_retry):
        logger.info(f"[生成轮次 {attempt + 1}/{max_retry}] 开始生成...")
        try:
            # 流式调用 LLM
            buffer = ""
            ai_output_lines = []  # 记录AI的所有输出（用于反馈）
            need_fix = False  # 是否需要修复（完整性校验失败）
            fix_prompt = ""  # 修复提示
            should_break_stream = False  # 是否应该中断流
            
            json_buffer = ""  # JSON 累积缓冲区
            brace_depth = 0  # 花括号深度
            in_string = False  # 是否在字符串内
            escape_next = False  # 下一个字符是否被转义
            
            async for chunk in chat_model.astream(messages):
                content = chunk.content if hasattr(chunk, 'content') else str(chunk)
                buffer += content
                
                # 按行解析
                lines = buffer.split('\n')
                buffer = lines[-1]  # 保留不完整的行
                
                for line in lines[:-1]:
                    line_stripped = line.strip()
                    if not line_stripped:
                        continue
                    
                    ai_output_lines.append(line_stripped)  # 记录输出
                    
                    # 逐字符处理，累积完整的 JSON 对象
                    instruction = None
                    for char in line:
                        # 处理转义
                        if escape_next:
                            if brace_depth > 0:
                                json_buffer += char
                            escape_next = False
                            continue
                        
                        if char == '\\':
                            if brace_depth > 0:
                                json_buffer += char
                            escape_next = True
                            continue
                        
                        # 处理字符串边界
                        if char == '"' and brace_depth > 0:
                            in_string = not in_string
                            json_buffer += char
                            continue
                        
                        # 只在字符串外计数花括号
                        if not in_string:
                            if char == '{':
                                brace_depth += 1
                                json_buffer += char
                            elif char == '}':
                                json_buffer += char
                                brace_depth -= 1
                                
                                # JSON 对象完整
                                if brace_depth == 0:
                                    instruction = try_parse_instruction(json_buffer)
                                    if not instruction:
                                        # 解析失败，可能是无效 JSON
                                        logger.warning(f"JSON 解析失败: {json_buffer}")
                                        # 尝试修复常见错误 (如末尾逗号)
                                        try:
                                            # 简单的清理逻辑，可以根据需要增强
                                            cleaned_json = json_buffer.replace(",}", "}").replace(",]", "]")
                                            instruction = try_parse_instruction(cleaned_json)
                                        except Exception:
                                            pass
                                            
                                        if not instruction:
                                            # JSON 解析失败，累积错误
                                            failed_instructions.append({
                                                "instruction": json_buffer[:100],
                                                "error": "JSON 解析失败"
                                            })
                                            yield {
                                                "type": "warning",
                                                "text": f"无法解析指令 JSON: {json_buffer[:50]}..."
                                            }
                                            # JSON 解析失败，累积错误但不立即打断，让LLM继续生成
                                            # 除非累积错误过多，才强制中断
                                            if len(failed_instructions) >= 5:
                                                should_break_stream = True
                                    
                                    json_buffer = ""
                                    if instruction:
                                        break  # 找到指令，处理它
                            elif brace_depth > 0:
                                json_buffer += char
                        elif brace_depth > 0:
                            json_buffer += char
                    
                    if instruction:
                        # ... (existing instruction processing logic) ...
                        # 解析成功，校验指令
                        try:
                            # ...
                            validate_instruction(instruction, schema)
                            apply_instruction(collected_data, instruction)
                            yield {
                                "type": "instruction",
                                "instruction": instruction
                            }
                            
                            # done logic ...
                            if instruction.get('op') == 'done':
                                logger.info("[Done 指令] 收到 done 指令，准备进行最终校验...")
                                
                                # 1. 检查是否有累积的指令错误
                                has_instruction_errors = len(failed_instructions) > 0
                                
                                # 2. 使用 Pydantic 进行数据完整性校验
                                validation_errors = []
                                try:
                                    validated_model = DynamicModel(**collected_data)
                                except ValidationError as e:
                                    # 格式化 Pydantic 错误
                                    validation_errors = e.errors()
                                
                                # 3. 如果有任何问题（指令错误 OR 数据校验失败），拒绝完成并反馈
                                if has_instruction_errors or validation_errors:
                                    logger.warning(f"[Done 拒绝] 指令错误: {len(failed_instructions)} 个, 数据校验问题: {len(validation_errors)} 个")
                                    
                                    feedback_parts = []
                                    
                                    # 构建指令错误反馈
                                    if failed_instructions:
                                        feedback_parts.append("【指令执行失败】以下指令解析或执行出错：")
                                        for item in failed_instructions:
                                            feedback_parts.append(f"- {item['error']}: {str(item['instruction'])[:100]}")
                                    
                                    # 构建数据完整性反馈
                                    if validation_errors:
                                        feedback_parts.append("\n【数据完整性缺失】以下字段未通过校验：")
                                        feedback_parts.append(format_validation_errors(validation_errors))
                                    
                                    feedback_text = "\n".join(feedback_parts)
                                    
                                    # 设置修复标志
                                    need_fix = True
                                    fix_prompt = f"""你发送了 done 指令，但生成过程存在错误或数据不完整：

{feedback_text}

当前已成功应用的数据状态：
```json
{json.dumps(collected_data, ensure_ascii=False, indent=2)}
```

请修正上述指令错误，并补充缺失的必填字段。
**重要**：请不要解释，直接输出修正用的 JSON 指令（set/append），修复完成后再次输出 {{"op":"done"}}
"""
                                    should_break_stream = True
                                else:
                                    # 一切完美，通过！
                                    logger.info("[Done 指令] ✅ 校验完美通过！")
                                    generation_completed = True
                                    yield {
                                        "type": "done",
                                        "success": True,
                                        "message": "生成完成",
                                        "final_data": validated_model.model_dump(mode='json')
                                    }
                                    return

                        except ValueError as e:
                            logger.warning(f"指令校验失败: {e}")
                            failed_instructions.append({"instruction": instruction, "error": str(e)})
                            yield {"type": "warning", "text": f"指令校验失败: {str(e)}"}
                            # 指令校验失败，累积错误但不中断，继续
                            # should_break_stream = True

                    else:
                        # 不是 JSON 指令，视为自然语言思考
                        # 只有在不在 JSON 累积过程中时才输出
                        if brace_depth == 0 and line_stripped:
                             yield {
                                "type": "thinking",
                                "text": line
                            }
                
                # 检查是否需要中断流
                if should_break_stream:
                    break
            
            # 处理残留的 JSON 缓冲区（多行 JSON 的最后部分）
            if json_buffer.strip() and brace_depth == 0:
                instruction = try_parse_instruction(json_buffer.strip())
                if instruction:
                    try:
                        validate_instruction(instruction, schema)
                        apply_instruction(collected_data, instruction)
                        yield {
                            "type": "instruction",
                            "instruction": instruction
                        }
                    except ValueError as e:
                        logger.warning(f"残留 JSON 指令校验失败: {e}")
            
            # 处理最后一行（如果有）
            if buffer.strip():
                instruction = try_parse_instruction(buffer.strip())
                if instruction:
                    try:
                        validate_instruction(instruction, schema)
                        apply_instruction(collected_data, instruction)
                        yield {
                            "type": "instruction",
                            "instruction": instruction
                        }
                        
                        if instruction.get('op') == 'done':
                            try:
                                validated_model = DynamicModel(**collected_data)
                                yield {
                                    "type": "done",
                                    "success": True,
                                    "message": "生成完成",
                                    # 将最终校验过的数据（包含注入的默认值）回传给前端，确保一致性
                                    "final_data": validated_model.model_dump(mode='json')
                                }
                                return
                            except ValidationError as e:
                                error_msg = format_validation_errors(e.errors())
                                logger.warning(f"完整性校验失败: {error_msg}")
                                # 设置修复标志，准备反馈给 LLM
                                need_fix = True
                                fix_prompt = f"""生成的数据不完整或有误，请修正以下问题：

{error_msg}

当前数据：
```json
{json.dumps(collected_data, ensure_ascii=False, indent=2)}
```

请继续生成缺失或错误的字段，完成后再次输出 {{"op":"done"}}
"""
                                should_break_stream = True
                    except ValueError as e:
                        logger.warning(f"指令校验失败: {e}")
                else:
                    yield {
                        "type": "thinking",
                        "text": buffer.strip()
                    }
            
            # 流结束后，处理各种情况
            
            # 情况1：完整性校验失败，需要修复
            if need_fix:
                logger.info(f"完整性校验失败，将反馈给LLM重新生成（尝试 {attempt + 1}/{max_retry}）")
                
                # 将AI输出和修复提示加入对话历史
                messages.append(AIMessage(content="\n".join(ai_output_lines)))
                messages.append(HumanMessage(content=fix_prompt))
                
                # 重试前等待，避免立即重试触发限流
                if attempt < max_retry - 1:
                    retry_delay = min(2 ** attempt, 5)  # 指数退避：1秒、2秒、4秒...
                    logger.info(f"等待 {retry_delay} 秒后重试...")
                    await asyncio.sleep(retry_delay)
                
                # 继续下一轮生成
                continue
            
            # 情况2：指令校验失败，需要反馈给LLM
            if failed_instructions:
                # 构建错误反馈消息
                error_summary = "\n".join([
                    f"- 指令: {json.dumps(item['instruction'], ensure_ascii=False)}\n  错误: {item['error']}"
                    for item in failed_instructions
                ])
                
                feedback_prompt = f"""
你生成的以下 {len(failed_instructions)} 条指令校验失败：

{error_summary}

当前已成功应用的数据：
```json
{json.dumps(collected_data, ensure_ascii=False, indent=2)}
```

请注意：
1. 检查字段路径是否正确
2. 对于数组字段，使用 append 操作前确保该字段是数组类型
3. 对于对象字段，使用 set 操作设置整个对象或使用嵌套路径设置子字段
4. 参考Schema定义，确保操作符与字段类型匹配

请修正这些错误并继续生成，完成后输出 {{"op":"done"}}
"""
                
                logger.info(f"反馈 {len(failed_instructions)} 个失败指令给LLM，重新生成")
                
                # 将AI输出和反馈加入对话历史
                messages.append(AIMessage(content="\n".join(ai_output_lines)))
                messages.append(HumanMessage(content=feedback_prompt))
                
                # 清空失败列表，准备下一轮
                failed_instructions = []
                
                # 重试前等待，避免立即重试触发限流
                if attempt < max_retry - 1:
                    retry_delay = min(2 ** attempt, 5)  # 指数退避：1秒、2秒、4秒...
                    logger.info(f"等待 {retry_delay} 秒后重试...")
                    await asyncio.sleep(retry_delay)
                
                # 继续下一轮生成
                continue
            
            # 如果流结束但没有 done 指令，可能是 max_tokens 限制或其他原因
            logger.warning("⚠️ LLM 流结束但未收到 done 指令")
            logger.info(f"当前已收集数据字段: {list(collected_data.keys())}")

            # 尝试隐式完成（尝试校验）
            try:
                # 使用 Pydantic 模型进行最终校验
                validated_model = DynamicModel(**collected_data)
                
                yield {
                    "type": "done",
                    "success": True,
                    "message": "生成结束 (自动补全)",
                    "final_data": validated_model.model_dump(mode='json')
                }
                generation_completed = True
                break
            except Exception as e:
                 logger.warning(f"流结束后的隐式校验失败: {e}")
                 # 如果真的校验失败，可能确实是截断了，需要用户反馈或者重试（这里暂不自动重试，因为已经是最后了）
                 pass
            logger.info(f"当前数据: {json.dumps(collected_data, ensure_ascii=False, indent=2)[:500]}...")
            
            # 尝试验证当前数据的完整性
            try:
                validated_model = DynamicModel(**collected_data)
                
                # 检查是否有 Optional 字段缺失（可能是被截断）
                schema_properties = schema.get("properties", {})
                missing_optional_fields = []
                for field_name, field_schema in schema_properties.items():
                    # 检查是否是 Optional 字段（不在 required 中）
                    is_optional = field_name not in schema.get("required", [])
                    # 如果是 Optional 字段但数据中没有（或为空列表/空字符串）
                    if is_optional:
                        field_value = collected_data.get(field_name)
                        if field_value is None or field_value == [] or field_value == "":
                            missing_optional_fields.append(field_name)
                
                # 如果有 Optional 字段缺失，很可能是 max_tokens 截断
                if missing_optional_fields:
                    logger.warning(f"⚠️ 虽然必填字段完整，但以下 Optional 字段缺失: {missing_optional_fields}")
                    logger.warning("结合 LLM 未发送 done 指令，怀疑是 max_tokens 截断")
                    yield {
                        "type": "warning",
                        "text": f"⚠️ 生成被截断（LLM 未发送 done 指令）。以下字段缺失：{', '.join(missing_optional_fields)}。\n\n原因可能是：\n1. max_tokens 设置过小（建议增加）\n2. 网络波动或服务限流\n\n建议：稍后重试或调整参数。"
                    }
                    # 尝试修复
                    if attempt < max_retry - 1:
                        logger.info(f"尝试自动补充缺失字段（尝试 {attempt + 1}/{max_retry}）")
                        fix_prompt = f"""
生成未完成，以下字段缺失：{', '.join(missing_optional_fields)}

当前数据：
```json
{json.dumps(collected_data, ensure_ascii=False, indent=2)}
```

请继续生成缺失的字段，完成后输出 {{"op":"done"}}
"""
                        messages.append(AIMessage(content="\n".join(ai_output_lines)))
                        messages.append(HumanMessage(content=fix_prompt))
                        
                        # 重试前等待
                        retry_delay = min(2 ** attempt, 5)
                        logger.info(f"等待 {retry_delay} 秒后重试...")
                        await asyncio.sleep(retry_delay)
                        
                        continue
                    else:
                        # 最后一轮了，直接返回不完整的数据
                        logger.warning("已达最大重试次数，返回不完整的数据")
                        generation_completed = True
                        yield {
                            "type": "done",
                            "success": True,
                            "message": f"生成完成（部分字段缺失：{', '.join(missing_optional_fields)}）"
                        }
                        return
                
                # 所有字段都有值，数据完整
                logger.info("✅ 数据完整性校验通过，虽然没有 done 指令，但数据是完整的")
                generation_completed = True
                yield {
                    "type": "done",
                    "success": True,
                    "message": "生成完成（LLM 未发送 done 指令，但数据完整）"
                }
                return
            except ValidationError as e:
                # 数据不完整，可能是 max_tokens 限制导致输出被截断
                error_msg = format_validation_errors(e.errors())
                logger.warning(f"❌ 数据不完整: {error_msg}")
                
                # 检查是否是第一轮就失败（可能是 max_tokens 太小）
                if attempt == 0:
                    yield {
                        "type": "error",
                        "text": f"⚠️ 生成被截断，原因可能是：\n1. max_tokens 设置过小（建议增加）\n2. 网络波动或服务限流\n\n建议：稍后重试或调整参数。"
                    }
                    logger.error("第一轮生成就被截断，强烈怀疑 max_tokens 过小")
                    break
                
                # 否则尝试修复
                logger.info(f"尝试自动修复缺失字段（尝试 {attempt + 1}/{max_retry}）")
                need_fix = True
                fix_prompt = f"""
生成被中断，数据不完整。缺失或错误的字段：

{error_msg}

当前数据：
```json
{json.dumps(collected_data, ensure_ascii=False, indent=2)}
```

请继续生成缺失的字段，完成后输出 {{"op":"done"}}
"""
                messages.append(AIMessage(content="\n".join(ai_output_lines)))
                messages.append(HumanMessage(content=fix_prompt))
                
                # 重试前等待
                if attempt < max_retry - 1:
                    retry_delay = min(2 ** attempt, 4)
                    logger.info(f"等待 {retry_delay} 秒后重试...")
                    await asyncio.sleep(retry_delay)
                
                continue
            
        except Exception as e:
            logger.error(f"生成过程出错: {e}")
            yield {
                "type": "error",
                "text": f"生成失败: {str(e)}"
            }
            break
    
    # 只有在未正常完成时才报告失败
    if not generation_completed:
        logger.error(f"❌ 生成失败：达到最大重试次数 {max_retry}")
        yield {
            "type": "error",
            "text": f"生成失败：达到最大重试次数 {max_retry}"
        }


def try_parse_instruction(line: str) -> Optional[Dict[str, Any]]:
    """尝试将一行文本解析为 JSON 指令
    
    Args:
        line: 文本行
        
    Returns:
        解析成功返回指令字典，否则返回 None
    """
    # 移除可能的 markdown 代码块标记
    line = line.strip()
    if line.startswith('```') or line.endswith('```'):
        return None
    
    # 尝试直接解析 JSON
    try:
        obj = json.loads(line)
        if isinstance(obj, dict) and 'op' in obj:
            return obj
    except json.JSONDecodeError:
        pass
    
    # 尝试提取 JSON 对象（支持嵌套结构）
    # 逐字符扫描，匹配完整的 JSON 对象
    start_idx = line.find('{')
    if start_idx == -1:
        return None
    
    # 从第一个 { 开始，匹配完整的 JSON 对象
    brace_count = 0
    in_string = False
    escape_next = False
    
    for i in range(start_idx, len(line)):
        char = line[i]
        
        # 处理字符串内的字符
        if escape_next:
            escape_next = False
            continue
        
        if char == '\\':
            escape_next = True
            continue
        
        if char == '"':
            in_string = not in_string
            continue
        
        # 只在字符串外计数花括号
        if not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                
                # 找到匹配的闭合括号
                if brace_count == 0:
                    json_str = line[start_idx:i+1]
                    try:
                        obj = json.loads(json_str)
                        if isinstance(obj, dict) and 'op' in obj:
                            return obj
                    except json.JSONDecodeError:
                        # 继续查找下一个可能的JSON对象
                        next_start = line.find('{', i+1)
                        if next_start != -1:
                            start_idx = next_start
                            brace_count = 0
                            in_string = False
                            escape_next = False
                        else:
                            return None
    
    return None

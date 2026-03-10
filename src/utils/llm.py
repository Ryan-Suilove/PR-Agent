"""
LLM配置和初始化
支持两种模式：
1. local: 使用本地Ollama服务
2. api: 使用OpenRouter API服务
"""

import sys
import io

# Windows兼容：强制使用UTF-8编码输出
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from .config import CONFIG
import json
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
import os

# 获取LLM模式配置
LLM_MODE = CONFIG['llm'].get('mode', 'local')

# 模型名称（兼容旧代码导出）
OLLAMA_MODEL = CONFIG['llm'].get('model', '')

# 检查是否启用调试模式（显示LLM原始响应）
DEBUG_SHOW_LLM_RESPONSE = CONFIG['llm'].get('debug_show_response', False)

# 性能优化：配置LLM参数（支持结构化输出）
llm_kwargs = {
    "temperature": CONFIG['llm'].get('temperature', 0),
    "num_predict": 16384,  # 最大输出长度
}

# 根据模式初始化LLM
if LLM_MODE == 'api':
    # API模式 - 使用OpenRouter
    from langchain_openai import ChatOpenAI

    API_BASE_URL = CONFIG['llm'].get('api_base_url', 'https://openrouter.ai/api/v1')
    API_KEY = CONFIG['llm'].get('api_key', '')
    # 优先使用 api_model，兼容旧配置中的 model 字段
    API_MODEL = CONFIG['llm'].get('api_model') or CONFIG['llm'].get('model', 'anthropic/claude-3-sonnet')

    if not API_KEY:
        print("[LLM] ⚠️ 警告: API模式未配置api_key，请在配置文件中设置")

    # 移除 Ollama 特有参数，使用 OpenAI API 兼容参数
    llm_kwargs.pop('num_predict', None)
    llm_kwargs.update({
        "model": API_MODEL,
        "base_url": API_BASE_URL,
        "api_key": API_KEY,
        "max_tokens": 16384,  # OpenAI API 使用 max_tokens 而非 num_predict
    })

    # API模式使用ChatOpenAI
    llm = ChatOpenAI(**llm_kwargs)
    print(f"[LLM] 🌐 API模式已启用")
    print(f"[LLM]    Base URL: {API_BASE_URL}")
    print(f"[LLM]    Model: {API_MODEL}")

else:
    # 本地模式 - 使用Ollama
    OLLAMA_BASE_URL = CONFIG['llm'].get('base_url', 'http://localhost:11434')

    llm_kwargs.update({
        "model": OLLAMA_MODEL,
        "base_url": OLLAMA_BASE_URL,
        "num_ctx": 81920,  # 增加上下文窗口
        "num_gpu": -1,
        "num_thread": 4,
    })

    llm_kwargs["format"] = "json"

    llm = ChatOllama(**llm_kwargs)
    print(f"[LLM] 🏠 本地模式已启用")
    print(f"[LLM]    Ollama URL: {OLLAMA_BASE_URL}")
    print(f"[LLM]    Model: {OLLAMA_MODEL}")


# 显示调试模式状态
if DEBUG_SHOW_LLM_RESPONSE:
    print("[LLM] 🐛 调试模式已启用（将显示LLM原始响应）")


class LLMResponseParser:
    """LLM响应解析器"""

    # 添加调用追踪，防止重复日志输出
    _call_tracking = {}
    _lock = asyncio.Lock()

    @staticmethod
    async def parse_json_with_retry(
        conversation: List,
        expected_schema: Dict[str, Any],
        max_retries: int = 3,
        parser_name: str = "unknown",
        timeout: int = 3600,
        custom_validator: Optional[callable] = None
    ) -> Optional[Dict[str, Any]]:
        """
        使用重试机制解析JSON响应，让LLM自我修正

        Args:
            conversation: 对话历史
            expected_schema: 期望的JSON schema
            max_retries: 最大重试次数
            parser_name: 解析器名称（用于日志）
            timeout: 单次请求超时时间（秒）
            custom_validator: 自定义验证函数，接收dict返回bool

        Returns:
            解析后的JSON对象，失败返回None
        """

        # 生成唯一的调用ID来追踪
        import hashlib
        call_id = hashlib.md5(f"{parser_name}_{id(conversation)}_{datetime.now().timestamp()}".encode()).hexdigest()[:8]

        for attempt in range(max_retries):
            try:
                # 使用锁防止并发打印
                async with LLMResponseParser._lock:
                    # 检查是否最近已经打印过（1秒内）
                    now = datetime.now().timestamp()
                    last_print_key = f"{parser_name}_{attempt}"
                    last_print_time = LLMResponseParser._call_tracking.get(last_print_key, 0)

                    # 只有距离上次打印超过1秒才打印
                    if now - last_print_time > 1.0:
                        print(f"[{parser_name}] 🔄 尝试 {attempt + 1}/{max_retries}，请求LLM中... (ID:{call_id})")
                        LLMResponseParser._call_tracking[last_print_key] = now

                        # 清理过期的追踪记录（超过10秒）
                        LLMResponseParser._call_tracking = {
                            k: v for k, v in LLMResponseParser._call_tracking.items()
                            if now - v < 10
                        }

                # 调用LLM（使用JSON格式），添加超时处理
                response = await asyncio.wait_for(
                    asyncio.to_thread(llm.invoke, conversation),
                    timeout=timeout
                )
                response_text = response.content

                # 提取token使用信息
                token_info = ""
                if hasattr(response, 'response_metadata'):
                    metadata = response.response_metadata
                    if 'eval_count' in metadata or 'prompt_eval_count' in metadata:
                        prompt_tokens = metadata.get('prompt_eval_count', 0)
                        completion_tokens = metadata.get('eval_count', 0)
                        total_tokens = prompt_tokens + completion_tokens
                        token_info = f" [Token: 输入={prompt_tokens}, 输出={completion_tokens}, 总计={total_tokens}]"
                    # OpenAI API格式
                    elif 'token_usage' in metadata:
                        usage = metadata['token_usage']
                        prompt_tokens = usage.get('prompt_tokens', 0)
                        completion_tokens = usage.get('completion_tokens', 0)
                        total_tokens = usage.get('total_tokens', 0)
                        token_info = f" [Token: 输入={prompt_tokens}, 输出={completion_tokens}, 总计={total_tokens}]"

                print(f"[{parser_name}] ✅ 收到响应，长度: {len(response_text)}{token_info}")

                # 调试模式：显示LLM原始响应和详细token信息
                if DEBUG_SHOW_LLM_RESPONSE:
                    print(f"\n{'='*60}")
                    print(f"[{parser_name}] 🐛 LLM原始响应:")
                    print(f"{'='*60}")

                    # 显示详细的token使用信息
                    if hasattr(response, 'response_metadata'):
                        metadata = response.response_metadata
                        print(f"📊 Token统计:")
                        # Ollama格式
                        if 'eval_count' in metadata:
                            print(f"  - 输入tokens (prompt_eval_count): {metadata.get('prompt_eval_count', 'N/A')}")
                            print(f"  - 输出tokens (eval_count): {metadata.get('eval_count', 'N/A')}")
                            if 'prompt_eval_count' in metadata and 'eval_count' in metadata:
                                total = metadata.get('prompt_eval_count', 0) + metadata.get('eval_count', 0)
                                print(f"  - 总计tokens: {total}")
                            if 'eval_duration' in metadata:
                                # 转换纳秒到秒
                                duration_s = metadata['eval_duration'] / 1e9
                                print(f"  - 生成耗时: {duration_s:.2f}秒")
                                if 'eval_count' in metadata and metadata['eval_count'] > 0:
                                    tokens_per_sec = metadata['eval_count'] / duration_s
                                    print(f"  - 生成速度: {tokens_per_sec:.2f} tokens/秒")
                        # OpenAI API格式
                        elif 'token_usage' in metadata:
                            usage = metadata['token_usage']
                            print(f"  - 输入tokens: {usage.get('prompt_tokens', 'N/A')}")
                            print(f"  - 输出tokens: {usage.get('completion_tokens', 'N/A')}")
                            print(f"  - 总计tokens: {usage.get('total_tokens', 'N/A')}")
                        print(f"{'='*60}")

                    # 如果响应很长，只显示前1000字符
                    if len(response_text) > 1000:
                        print(response_text[:1000])
                        print(f"\n... (还有 {len(response_text) - 1000} 个字符)")
                    else:
                        print(response_text)
                    print(f"{'='*60}\n")

                # 尝试解析JSON
                try:
                    result = json.loads(response_text)
                    print(f"[{parser_name}] 📝 JSON解析成功，验证schema中...")

                    # 验证schema - 优先使用自定义验证器
                    if custom_validator:
                        if custom_validator(result):
                            print(f"[{parser_name}] ✅ 自定义验证通过，解析完成！")
                            return result
                        else:
                            print(f"[{parser_name}] ⚠️ 自定义验证失败")
                            print(f"[{parser_name}] 实际字段: {list(result.keys())}")
                            error_msg = "JSON结构不符合自定义验证规则"
                    elif LLMResponseParser._validate_schema(result, expected_schema):
                        print(f"[{parser_name}] ✅ Schema验证通过，解析完成！")
                        return result
                    else:
                        print(f"[{parser_name}] ⚠️ Schema验证失败")
                        print(f"[{parser_name}] 期望字段: {list(expected_schema.keys())}")
                        print(f"[{parser_name}] 实际字段: {list(result.keys())}")
                        error_msg = "JSON结构不符合预期schema"

                except json.JSONDecodeError as e:
                    print(f"[{parser_name}] ⚠️ JSON解析失败: {str(e)}")
                    print(f"[{parser_name}] 响应前200字符: {response_text[:200]}...")
                    error_msg = f"JSON格式错误: {str(e)}"

                # 记录失败
                LLMResponseParser._log_parse_failure(
                    parser_name=parser_name,
                    attempt=attempt + 1,
                    response_text=response_text,
                    error_msg=error_msg
                )

                # 如果还有重试机会，让LLM自我修正
                if attempt < max_retries - 1:
                    print(f"[{parser_name}] 🔄 准备重试 {attempt + 2}/{max_retries}，请求LLM自我修正...")

                    conversation.append(HumanMessage(content=response_text))
                    conversation.append(HumanMessage(content=f"""
上一次的响应解析失败：{error_msg}

请严格按照以下要求重新生成：
1. 只输出纯JSON，不要添加任何解释文字
2. 不要使用markdown代码块标记（如 ```json）
3. 确保JSON格式完全正确（双引号、逗号、括号匹配）
4. 必须包含以下字段：{list(expected_schema.keys())}

请重新输出：
"""))

            except asyncio.TimeoutError:
                print(f"[{parser_name}] ⏱️ 请求超时（{timeout}秒）")
                LLMResponseParser._log_parse_failure(
                    parser_name=parser_name,
                    attempt=attempt + 1,
                    response_text="",
                    error_msg=f"Timeout after {timeout} seconds"
                )

                if attempt < max_retries - 1:
                    print(f"[{parser_name}] 将在下次尝试中使用更长的超时时间...")
                    timeout = int(timeout * 1.5)  # 增加超时时间

            except Exception as e:
                print(f"[{parser_name}] ❌ 异常: {str(e)}")
                import traceback
                print(f"[{parser_name}] 堆栈追踪:\n{traceback.format_exc()}")
                LLMResponseParser._log_parse_failure(
                    parser_name=parser_name,
                    attempt=attempt + 1,
                    response_text="",
                    error_msg=f"Exception: {str(e)}\n{traceback.format_exc()}"
                )

                if attempt < max_retries - 1:
                    conversation.append(HumanMessage(content=f"发生错误: {str(e)}，请重试"))

        # 所有重试都失败
        print(f"[{parser_name}] ❌ 所有重试均失败")
        return None

    @staticmethod
    def _validate_schema(data: Dict[str, Any], schema: Dict[str, Any]) -> bool:
        """验证JSON是否符合schema"""
        # 简单验证：检查必需字段是否存在
        for key in schema.keys():
            if key not in data:
                print(f"缺少字段: {key}")
                return False
        return True

    @staticmethod
    def _log_parse_failure(
        parser_name: str,
        attempt: int,
        response_text: str,
        error_msg: str
    ):
        """记录解析失败的详细信息"""
        try:
            # 确保logs目录存在
            log_dir = "logs/parse_failures"
            os.makedirs(log_dir, exist_ok=True)

            # 生成日志文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = os.path.join(
                log_dir,
                f"{parser_name}_{timestamp}_attempt{attempt}.log"
            )

            # 写入日志
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(f"Parser: {parser_name}\n")
                f.write(f"Attempt: {attempt}\n")
                f.write(f"Timestamp: {timestamp}\n")
                f.write(f"Error: {error_msg}\n")
                f.write(f"\n{'='*60}\n")
                f.write(f"Response Text:\n")
                f.write(f"{'='*60}\n")
                f.write(response_text)

            print(f"[{parser_name}] 📝 失败日志已保存: {log_file}")

        except Exception as e:
            print(f"[{parser_name}] ⚠️ 无法保存日志: {str(e)}")


# 导出解析器
parser = LLMResponseParser()
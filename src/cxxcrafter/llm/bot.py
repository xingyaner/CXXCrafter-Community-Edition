import openai
import tiktoken
import logging
import time
import os

# 保持您环境能运行的导入方式
try:
    from src.cxxcrafter.config import LLM_MODEL, LLM_API_KEY, LLM_BASE_URL
except ImportError:
    from src.cxxcrafter.config import LLM_MODEL, LLM_API_KEY, LLM_BASE_URL


# --- 兼容性接口：供 cli.py 调用 ---
def get_sdk_token_counts():
    """返回 GPTBot 累积的全局 Token 统计"""
    return GPTBot.sdk_input_tokens, GPTBot.sdk_output_tokens


class GPTBot:
    # --- 核心统计变量：绑定在类上，防止多模块加载导致的变量隔离 ---
    sdk_input_tokens = 0
    sdk_output_tokens = 0

    def __init__(self, system_prompt=None):
        content = system_prompt if system_prompt is not None else "You are a premier expert in software building."
        self.messages = [{"role": "system", "content": content}]
        self.client = openai.OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
        self.model = LLM_MODEL
        self.logger = logging.getLogger(__name__)
        self.last_reasoning = ""

    def _clear_history_reasoning(self):
        """下一轮对话前清理思维链，节省带宽"""
        for msg in self.messages:
            if isinstance(msg, dict) and msg.get("role") == "assistant" and "reasoning_content" in msg:
                del msg["reasoning_content"]

    def inference(self, message=''):
        self._clear_history_reasoning()
        self.messages.append({"role": "user", "content": message})

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.messages,
                    timeout=300
                )
                msg_obj = response.choices[0].message
                self.last_reasoning = getattr(msg_obj, 'reasoning_content', "")
                content = msg_obj.content

                # 累加到类属性（确保跨 src.cxxcrafter 和 cxxcrafter 命名空间共享）
                if hasattr(response, 'usage') and response.usage:
                    GPTBot.sdk_input_tokens += response.usage.prompt_tokens
                    GPTBot.sdk_output_tokens += response.usage.completion_tokens

                self.messages.append({
                    "role": "assistant",
                    "content": content,
                    "reasoning_content": self.last_reasoning
                })

                if self.last_reasoning:
                    self.logger.info(f"--- [REASONER THOUGHTS] ---\n{self.last_reasoning[:500]}...\n")
                return content

            except Exception as e:
                self.logger.warning(f"API Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                raise e

    def calculate_message_length(self, message):
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(str(message)))
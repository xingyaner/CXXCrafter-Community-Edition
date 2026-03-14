import openai
import tiktoken
import logging
from src.cxxcrafter.config import LLM_MODEL, LLM_API_KEY, LLM_BASE_URL

global_input_token_count = 0
global_output_token_count = 0
sdk_global_input_token_count = 0
sdk_global_output_token_count = 0


def get_sdk_token_counts():
    global sdk_global_input_token_count, sdk_global_output_token_count
    return sdk_global_input_token_count, sdk_global_output_token_count


def token_count_decorator(func):
    def wrapper(self, *args, **kwargs):
        global global_input_token_count, global_output_token_count
        message = kwargs.get('message', args[0] if args else '')
        input_tokens = self.calculate_message_length(message)
        global_input_token_count += input_tokens
        self.input_token_count += input_tokens
        result = func(self, *args, **kwargs)
        # 注意：推理模式下返回值是最终 content，SDK 统计会包含思维链 token
        output_tokens = self.calculate_message_length(result)
        global_output_token_count += output_tokens
        self.output_token_count += output_tokens
        return result

    return wrapper


class GPTBot:
    def __init__(self, system_prompt=None):
        content = system_prompt if system_prompt is not None else "You are a premier expert in software building."
        self.messages = [{"role": "system", "content": content}]
        self.client = openai.OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
        self.model = LLM_MODEL
        self.logger = logging.getLogger(__name__)
        self.input_token_count = 0
        self.output_token_count = 0
        self.last_reasoning = ""  # 记录最近一次思维链内容

    def _clear_history_reasoning(self):
        """
        按照官方文档要求：在下一轮对话开始时，清理历史 assistant 消息中的 reasoning_content
        """
        for msg in self.messages:
            if msg.get("role") == "assistant" and "reasoning_content" in msg:
                del msg["reasoning_content"]

    @token_count_decorator
    def inference(self, message=''):
        self._clear_history_reasoning()
        self.messages.append({"role": "user", "content": message})

        # 调用 API (推理模式下自动处理 reasoning_content)
        response = self.client.chat.completions.create(
            model=self.model,
            messages=self.messages
        )

        msg_obj = response.choices[0].message
        self.last_reasoning = getattr(msg_obj, 'reasoning_content', "")
        content = msg_obj.content

        # 记录 SDK Token 使用
        global sdk_global_input_token_count, sdk_global_output_token_count
        sdk_global_input_token_count += response.usage.prompt_tokens
        sdk_global_output_token_count += response.usage.completion_tokens

        # 存入历史（当前轮次保留 reasoning 以备可能的 log 需要）
        self.messages.append({
            "role": "assistant",
            "content": content,
            "reasoning_content": self.last_reasoning
        })

        if self.last_reasoning:
            self.logger.info(f"--- [REASONER THOUGHTS] ---\n{self.last_reasoning[:500]}...\n")

        return content

    @token_count_decorator
    def inference2(self, context=128000, message=''):
        self._clear_history_reasoning()
        self.messages.append({"role": "user", "content": message})

        # 简化版上下文窗口管理
        while self.calculate_total_length(self.messages) >= context:
            if len(self.messages) > 2:  # 保留 system 和最新的消息
                self.messages.pop(1)
            else:
                break

        response = self.client.chat.completions.create(
            model=self.model,
            messages=self.messages
        )

        msg_obj = response.choices[0].message
        self.last_reasoning = getattr(msg_obj, 'reasoning_content', "")
        content = msg_obj.content

        global sdk_global_input_token_count, sdk_global_output_token_count
        sdk_global_input_token_count += response.usage.prompt_tokens
        sdk_global_output_token_count += response.usage.completion_tokens

        self.messages.append({
            "role": "assistant",
            "content": content,
            "reasoning_content": self.last_reasoning
        })
        return content

    def calculate_message_length(self, message):
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(str(message)))

    def calculate_total_length(self, messages):
        enc = tiktoken.get_encoding("cl100k_base")
        total_length = 0
        for message in messages:
            total_length += len(enc.encode(str(message.get('content', ''))))
            total_length += len(enc.encode(str(message.get('reasoning_content', ''))))
        return total_length
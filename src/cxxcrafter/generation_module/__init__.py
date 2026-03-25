from agent_tools import read_file_content
import os
import logging
from .utils import save_dockerfile, extract_dockerfile_content, resave_dockerfile
from .template.prompt_template import get_initial_prompt, prompt_template_for_modification
from .utils import save_dockerfile, extract_dockerfile_content, resave_dockerfile
from .template.prompt_template import get_initial_prompt, prompt_template_for_modification
from .template.prompt_template import get_initial_prompt
from src.cxxcrafter.llm.bot import GPTBot


class DockerfileGenerator:
    def __init__(self, project_name, project_path, environment_requirement, dependency, docs, project_info=None):
        self.project_name = project_name
        self.project_path = project_path
        self.environment_requirement = environment_requirement
        self.dependency = dependency
        self.docs = docs
        self.project_info = project_info
        self.logger = logging.getLogger(__name__)

    def generate_dockerfile(self):
        self.logger.info(f"Generating initial Dockerfile for {self.project_name}...")
        user_intention_data = self.project_info if self.project_info else {}
        prompt_text = get_initial_prompt(
            self.project_name,
            user_intention_data,
            self.environment_requirement,
            self.dependency,
            self.docs
        )
        bot = GPTBot(system_prompt="You are a premier expert in C/C++ building.")
        response = bot.inference(str(prompt_text))
        try:
            dockerfile_content = extract_dockerfile_content(response)
            from src.cxxcrafter.init import get_playground_dir
            save_path = os.path.join(get_playground_dir(), self.project_name)
            os.makedirs(save_path, exist_ok=True)
            save_dockerfile(save_path, dockerfile_content)
            return bot.last_reasoning
        except Exception as e:
            self.logger.error(f"Failed to process LLM response: {e}")
            raise e


class DockerfileModifier:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # 保持对话上下文
        self.bot = GPTBot(system_prompt="You are an expert build engineer specializing in debugging.")

    def modify_dockerfile(self, dockerfile_path, error_message):
        """
        [被动注入版]：自动读取 400 行日志并喂给模型
        """
        self.logger.info("Modifying Dockerfile (Injecting 400 lines of log)...")

        if not os.path.exists(dockerfile_path):
            raise FileNotFoundError(f"Dockerfile not found: {dockerfile_path}")

        # 1. 物理读取报错日志
        log_path = 'fuzz_build_log_file/fuzz_build_log.txt'
        log_res = read_file_content(log_path, tail_lines=400)

        # 如果读取失败，提供提示信息
        log_tail = log_res.get('content', "Warning: Could not retrieve build log content.")

        # 2. 读取当前 Dockerfile
        with open(dockerfile_path, 'r', encoding='utf-8') as f:
            last_content = f.read()

        # 3. 组装 Prompt（注入日志）
        prompt = prompt_template_for_modification.format(
            log_tail=log_tail,
            last_dockerfile_content=last_content,
            feedback_message=error_message
        )

        # 4. 执行推理
        response = self.bot.inference(str(prompt))

        # 5. 提取并保存
        try:
            new_content = extract_dockerfile_content(response)
            resave_dockerfile(dockerfile_path, new_content)
            return self.bot.last_reasoning
        except Exception as e:
            self.logger.error(f"Modifier failed to extract Dockerfile: {e}")
            return getattr(self.bot, 'last_reasoning', "")
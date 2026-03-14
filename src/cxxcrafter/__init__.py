from .init import ensure_all_directories_exist
from .cli import CXXCrafter
import os
import logging
from src.cxxcrafter.generation_module.utils import save_dockerfile, extract_dockerfile_content
from src.cxxcrafter.generation_module.template.prompt_template import get_initial_prompt
from src.cxxcrafter.llm.bot import GPTBot


ensure_all_directories_exist()


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

            # 配套修改：返回思维链
            return bot.last_reasoning
        except Exception as e:
            self.logger.error(f"Failed to process LLM response: {e}")
            raise e


class DockerfileModifier:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.bot = GPTBot(system_prompt="You are an expert at debugging build errors.")

    def modify_dockerfile(self, dockerfile_path, error_message):
        from src.cxxcrafter.generation_module.template.prompt_template import prompt_template_for_modification
        from src.cxxcrafter.generation_module.utils import resave_dockerfile

        with open(dockerfile_path, 'r', encoding='utf-8') as f:
            last_content = f.read()

        prompt = prompt_template_for_modification.format(
            last_dockerfile_content=last_content,
            feedback_message=error_message
        )

        response = self.bot.inference(str(prompt))

        try:
            new_content = extract_dockerfile_content(response)
            resave_dockerfile(dockerfile_path, new_content)

            # 配套修改：返回修改时的思维链
            return self.bot.last_reasoning
        except Exception as e:
            self.logger.error(f"Failed to resave modified Dockerfile: {e}")
            raise e
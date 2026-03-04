import os
import logging
from datetime import datetime
from cxxcrafter.log_utils import setup_logging, log_the_dockerfile, log_the_error_message
from cxxcrafter.generation_module import DockerfileGenerator, DockerfileModifier
from cxxcrafter.utils import save_successful_dockerfile
from cxxcrafter.parsing_module import parser
from cxxcrafter.init import get_log_dir, get_playground_dir, get_solution_base_dir
from cxxcrafter.llm.bot import get_sdk_token_counts

# 桥接您的构建工具
from agent_tools import run_fuzz_build_streaming, read_file_content
from cxxcrafter.execution_module.discriminator import build_success_check_2

class CXXCrafter:
    def __init__(self, project_path, project_info=None, oss_fuzz_root_path=None):
        self.project_path = project_path
        self.project_info = project_info
        self.oss_fuzz_root_path = oss_fuzz_root_path
        self.start_time = datetime.now().strftime('%Y%m%d_%H%M')
        self.project_name = os.path.basename(project_path)
        self.dockerfile_path = os.path.join(get_playground_dir(), self.project_name, 'Dockerfile')
        self.log_file = f"{get_log_dir()}/{self.project_name}_{self.start_time}.log"
        self.history_dir = None
        self.flag_version = 1
        self.modifier = DockerfileModifier()

        setup_logging(self.log_file, self.project_name)
        self.logger = logging.getLogger(__name__)
        self.logger.disabled = False

    def parse_project(self):
        self.logger.info('Parsing Module Starts')
        (self.project_name, self.project_path, self.environment_requirement,
         self.build_system_name, self.entry_file, self.potential_dependency, 
         self.docs) = parser(self.project_path)
        self.logger.info('Parsing Module Finishes')

    def generate_dockerfile(self):
        self.logger.info('Generation Module Starts')
        dockerfile_generator = DockerfileGenerator(
            self.project_name, self.project_path, 
            self.environment_requirement, self.potential_dependency, 
            self.docs, project_info=self.project_info)
        
        dockerfile_generator.generate_dockerfile()
        self.logger.info('Generation Module Finishes')

        self.history_dir = os.path.join(os.path.dirname(self.dockerfile_path), f'history-{self.start_time}')
        os.makedirs(self.history_dir, exist_ok=True)
        log_the_dockerfile(self.dockerfile_path, self.flag_version, self.history_dir)
    
    def modify_dockerfile(self, error_message):
        self.logger.info('Modifier Module Starts')
        # 调用时确保传递的是真正的错误日志内容
        self.modifier.modify_dockerfile(self.dockerfile_path, error_message)
        self.logger.info('Modifier Module Finishes')
        self.flag_version += 1
        log_the_dockerfile(self.dockerfile_path, self.flag_version, self.history_dir)

    def execute_dockerfile(self):
        """
        [Baseline 改写] 修复日志传递逻辑
        """
        self.logger.info('--- [Baseline] Execution via run_fuzz_build_streaming ---')
        
        # 1. 执行构建
        run_fuzz_build_streaming(
            project_name=self.project_name,
            oss_fuzz_path=self.oss_fuzz_root_path,
            sanitizer=self.project_info.get('sanitizer', 'address'),
            engine=self.project_info.get('engine', 'libfuzzer'),
            architecture=self.project_info.get('architecture', 'x86_64'),
            mount_path=None 
        )
        
        # 2. 【核心修复】显式从日志文件读取内容
        # 否则 Baseline 不知道 ./autogen.sh 不存在
        log_res = read_file_content('fuzz_build_log_file/fuzz_build_log.txt', tail_lines=200)
        real_log_content = log_res.get('content', 'No log content available.')
        
        # 3. 使用判别器分析真实日志
        flag, error = build_success_check_2(
            os.path.dirname(self.dockerfile_path), 
            real_log_content, 
            build_system_name=self.build_system_name
        )
        return flag, error

    def run(self):
        self.parse_project()
        self.generate_dockerfile()
        while True:
            flag_success, error_message = self.execute_dockerfile()
            if not flag_success:
                self.logger.error(f"Execution failed: {error_message}")
                log_the_error_message(error_message, self.flag_version, self.history_dir)
                if self.flag_version >= 10:
                    return self.project_name, False
                self.modify_dockerfile(error_message)
            else:
                save_successful_dockerfile(self.dockerfile_path, self.project_name, get_solution_base_dir())
                return self.project_name, True

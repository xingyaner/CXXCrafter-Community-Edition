import os
import logging
import time # 新增：用于计时
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
        
        # --- 统计初始化 ---
        self.start_wall_time = time.time()
        self.start_in_tokens, self.start_out_tokens = get_sdk_token_counts()
        
        self.start_time_str = datetime.now().strftime('%Y%m%d_%H%M')
        self.project_name = os.path.basename(project_path)
        self.dockerfile_path = os.path.join(get_playground_dir(), self.project_name, 'Dockerfile')
        self.log_file = f"{get_log_dir()}/{self.project_name}_{self.start_time_str}.log"
        self.history_dir = None
        self.flag_version = 0 # 修复轮数计数
        self.modifier = DockerfileModifier()

        setup_logging(self.log_file, self.project_name)
        self.logger = logging.getLogger(__name__)
        self.logger.disabled = False

    def _calculate_lines_modified(self):
        """统计最终生成的 Dockerfile 行数作为修改行数"""
        if os.path.exists(self.dockerfile_path):
            try:
                with open(self.dockerfile_path, 'r', encoding='utf-8') as f:
                    return len(f.readlines())
            except Exception:
                return 0
        return 0

    def print_final_report(self, is_success):
        """按照特定格式输出最终 Baseline 报告"""
        end_time = time.time()
        end_in_tokens, end_out_tokens = get_sdk_token_counts()
        
        duration_min = (end_time - self.start_wall_time) / 60
        total_tokens = (end_in_tokens - self.start_in_tokens) + (end_out_tokens - self.start_out_tokens)
        lines_modified = self._calculate_lines_modified()
        
        result_icon = "✅ SUCCESS" if is_success else "❌ FAILURE"
        
        report = (
            f"\n{'='*60}\n"
            f"🏁 FINAL BASELINE REPORT: {self.project_name}\n"
            f"[RESULT]           {result_icon}\n"
            f"[DISCUSSION]       NO\n"
            f"[REPAIR ROUNDS]    {self.flag_version}\n"
            f"[TOKEN USAGE]      {total_tokens}\n"
            f"[FILES MODIFIED]   {1 if lines_modified > 0 else 0}\n"
            f"[LINES MODIFIED]   {lines_modified}\n"
            f"[TIME COST]        {duration_min:.2f} minutes\n"
            f"{'='*60}\n"
        )
        # 同时输出到终端和日志文件
        print(report)
        self.logger.info(report)

    def parse_project(self):
        self.logger.info('Parsing Module Starts')
        (self.project_name, self.project_path, self.environment_requirement,
         self.build_system_name, self.entry_file, self.potential_dependency, 
         self.docs) = parser(self.project_path)
        self.logger.info('Parsing Module Finishes')

    def generate_dockerfile(self):
        self.logger.info('Generation Module Starts')
        # 第一次生成计为第 1 轮
        self.flag_version += 1
        dockerfile_generator = DockerfileGenerator(
            self.project_name, self.project_path, 
            self.environment_requirement, self.potential_dependency, 
            self.docs, project_info=self.project_info)
        
        dockerfile_generator.generate_dockerfile()
        self.logger.info('Generation Module Finishes')

        self.history_dir = os.path.join(os.path.dirname(self.dockerfile_path), f'history-{self.start_time_str}')
        os.makedirs(self.history_dir, exist_ok=True)
        log_the_dockerfile(self.dockerfile_path, self.flag_version, self.history_dir)
    
    def modify_dockerfile(self, error_message):
        self.logger.info('Modifier Module Starts')
        # 每次修改计为新的一轮
        self.flag_version += 1
        self.modifier.modify_dockerfile(self.dockerfile_path, error_message)
        self.logger.info('Modifier Module Finishes')
        log_the_dockerfile(self.dockerfile_path, self.flag_version, self.history_dir)

    def execute_dockerfile(self):
        self.logger.info(f'--- [Baseline Round {self.flag_version}] Execution ---')
        run_fuzz_build_streaming(
            project_name=self.project_name,
            oss_fuzz_path=self.oss_fuzz_root_path,
            sanitizer=self.project_info.get('sanitizer', 'address'),
            engine=self.project_info.get('engine', 'libfuzzer'),
            architecture=self.project_info.get('architecture', 'x86_64'),
            mount_path=None 
        )
        
        log_res = read_file_content('fuzz_build_log_file/fuzz_build_log.txt', tail_lines=200)
        real_log_content = log_res.get('content', 'No log content available.')
        
        flag, error = build_success_check_2(
            os.path.dirname(self.dockerfile_path), 
            real_log_content, 
            build_system_name=self.build_system_name
        )
        return flag, error

    def run(self):
        try:
            self.parse_project()
            self.generate_dockerfile()
            while True:
                flag_success, error_message = self.execute_dockerfile()
                if not flag_success:
                    self.logger.error(f"Execution failed: {error_message}")
                    log_the_error_message(error_message, self.flag_version, self.history_dir)
                    
                    # 达到 10 次上限，打印报告并退出
                    if self.flag_version >= 10:
                        self.print_final_report(False)
                        return self.project_name, False
                    
                    self.modify_dockerfile(error_message)
                else:
                    save_successful_dockerfile(self.dockerfile_path, self.project_name, get_solution_base_dir())
                    self.print_final_report(True)
                    return self.project_name, True
        except Exception as e:
            self.logger.critical(f"Unexpected error in run loop: {e}")
            self.print_final_report(False)
            raise e

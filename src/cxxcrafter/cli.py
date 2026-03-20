import os
import logging
import time
import sys
from datetime import datetime

# --- 关键：统一导入路径，移除 src. 前缀 ---
from src.cxxcrafter.log_utils import (
    setup_logging, log_the_dockerfile, log_the_error_message,
    log_the_reasoning, LoggerWriter
)
from src.cxxcrafter.generation_module import DockerfileGenerator, DockerfileModifier
from src.cxxcrafter.utils import save_successful_dockerfile
from src.cxxcrafter.parsing_module import parser
from src.cxxcrafter.init import get_log_dir, get_playground_dir, get_solution_base_dir
from src.cxxcrafter.llm.bot import get_sdk_token_counts
from agent_tools import run_fuzz_build_and_validate, read_file_content


class CXXCrafter:
    def __init__(self, project_path, project_info=None, oss_fuzz_root_path=None):
        self.project_path = project_path
        self.project_info = project_info
        self.oss_fuzz_root_path = oss_fuzz_root_path

        self.start_wall_time = time.time()
        self.start_in_tokens, self.start_out_tokens = get_sdk_token_counts()

        self.start_time_str = datetime.now().strftime('%Y%m%d_%H%M')
        self.project_name = os.path.basename(project_path)
        self.dockerfile_path = os.path.join(get_playground_dir(), self.project_name, 'Dockerfile')
        self.log_file = f"{get_log_dir()}/{self.project_name}_{self.start_time_str}.log"
        self.history_dir = None
        self.flag_version = 0
        self.modifier = DockerfileModifier()

        # 1. 启动标准日志配置
        setup_logging(self.log_file, self.project_name)
        self.logger = logging.getLogger(__name__)
        self.logger.disabled = False

        # 2. 【核心修改】：接管全局输出
        # 劫持后，所有的 print() 内容都会变成 logger.info 并存入 self.log_file
        sys.stdout = LoggerWriter(self.logger, logging.INFO)
        # 同时捕获标准错误，确保代码报错堆栈也能存入日志
        sys.stderr = LoggerWriter(self.logger, logging.ERROR)


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
        end_time = time.time()
        end_in_tokens, end_out_tokens = get_sdk_token_counts()

        duration_min = (end_time - self.start_wall_time) / 60
        total_tokens = (end_in_tokens - self.start_in_tokens) + (end_out_tokens - self.start_out_tokens)
        lines_modified = self._calculate_lines_modified()

        result_icon = "✅ SUCCESS" if is_success else "❌ FAILURE"

        report = (
            f"\n{'=' * 60}\n"
            f"🏁 FINAL BASELINE REPORT: {self.project_name}\n"
            f"[RESULT]           {result_icon}\n"
            f"[DISCUSSION]       NO\n"
            f"[REPAIR ROUNDS]    {self.flag_version}\n"
            f"[TOKEN USAGE]      {total_tokens}\n"
            f"[FILES MODIFIED]   {1 if lines_modified > 0 else 0}\n"
            f"[LINES MODIFIED]   {lines_modified}\n"
            f"[TIME COST]        {duration_min:.2f} minutes\n"
            f"{'=' * 60}\n"
        )
        # 此时的 print 会自动进入日志
        print(report)

    def parse_project(self):
        self.logger.info('Parsing Module Starts')
        (self.project_name, self.project_path, self.environment_requirement,
         self.build_system_name, self.entry_file, self.potential_dependency, 
         self.docs) = parser(self.project_path)
        self.logger.info('Parsing Module Finishes')

    def generate_dockerfile(self):
        self.logger.info('Generation Module Starts')
        self.flag_version += 1
        dockerfile_generator = DockerfileGenerator(
            self.project_name, self.project_path,
            self.environment_requirement, self.potential_dependency,
            self.docs, project_info=self.project_info)

        reasoning = dockerfile_generator.generate_dockerfile()
        self.logger.info('Generation Module Finishes')

        self.history_dir = os.path.join(os.path.dirname(self.dockerfile_path), f'history-{self.start_time_str}')
        os.makedirs(self.history_dir, exist_ok=True)

        log_the_dockerfile(self.dockerfile_path, self.flag_version, self.history_dir)
        log_the_reasoning(reasoning, self.flag_version, self.history_dir)

    def modify_dockerfile(self, error_message):
        self.logger.info('Modifier Module Starts')
        self.flag_version += 1
        reasoning = self.modifier.modify_dockerfile(self.dockerfile_path, error_message)
        self.logger.info('Modifier Module Finishes')
        log_the_dockerfile(self.dockerfile_path, self.flag_version, self.history_dir)
        log_the_reasoning(reasoning, self.flag_version, self.history_dir)

    def execute_dockerfile(self):
        """
        [物理验证增强版]
        1. 详细打印每一项验证结果（控制台+日志）。
        2. 仅当 Step 1 & 6 通过时判定成功。
        3. 对 LLM 隐藏具体失败细节。
        """
        self.logger.info(f'--- [Baseline Round {self.flag_version}] Starting Physical Validation ---')

        # 1. 执行验证工具
        from agent_tools import run_fuzz_build_and_validate
        result = run_fuzz_build_and_validate(
            project_name=self.project_name,
            oss_fuzz_path=self.oss_fuzz_root_path,
            sanitizer=self.project_info.get('sanitizer', 'address'),
            engine=self.project_info.get('engine', 'libfuzzer'),
            architecture=self.project_info.get('architecture', 'x86_64'),
            mount_path=None
        )

        validation_report = result.get("validation_report", {})

        # --- 核心修改：在控制台/日志中展示每一项简要结果 ---
        print(f"\n[Validation Details - Round {self.flag_version}]")
        print("-" * 40)
        # 定义展示顺序和名称映射
        step_names = {
            "step_1_static_output": "1. Static Binary Output  ",
            "step_2_sanitizer_injected": "2. Sanitizer Injection   ",
            "step_3_engine_linked": "3. Fuzzing Engine Link  ",
            "step_4_logic_linked": "4. Project Logic Link   ",
            "step_5_dependencies_ok": "5. Library Dependencies ",
            "step_6_runtime_stability": "6. Runtime Stability    "
        }

        for key, display_name in step_names.items():
            info = validation_report.get(key, {"status": "skipped", "details": "N/A"})
            status_str = info['status'].upper()
            # 这里的 print 会通过 LoggerWriter 同时写入终端和日志文件
            print(f"  {display_name}: [{status_str}]")
        print("-" * 40 + "\n")

        # --- 核心判定准则 ---
        step_1_pass = validation_report.get("step_1_static_output", {}).get("status") == "pass"
        step_6_pass = validation_report.get("step_6_runtime_stability", {}).get("status") == "pass"
        flag_success = step_1_pass and step_6_pass

        # --- 对 LLM 的反馈控制 ---
        if flag_success:
            feedback_msg = "SUCCESS"
        else:
            feedback_msg = "Build failed. The generated configuration did not produce a valid and stable fuzzing binary."

        return flag_success, feedback_msg

    def run(self):
        try:
            self.parse_project()
            self.generate_dockerfile()
            while True:
                flag_success, error_message = self.execute_dockerfile()
                if not flag_success:
                    self.logger.error(f"Execution failed: {error_message}")
                    log_the_error_message(error_message, self.flag_version, self.history_dir)
                    if self.flag_version >= 10:
                        self.print_final_report(False)
                        return self.project_name, False
                    self.modify_dockerfile(error_message)
                else:
                    save_successful_dockerfile(self.dockerfile_path, self.project_name, get_solution_base_dir())
                    self.print_final_report(True)
                    return self.project_name, True
        except Exception as e:
            # 由于 sys.stderr 已被劫持，这里的错误详情也会入库
            self.print_final_report(False)
            raise e
        finally:
            # 3. 【可选】恢复流，防止影响 run.py 后续的非 CXXCrafter 逻辑
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__
import os
import logging
import logging.config
import sys

class LoggerWriter:
    """
    将 sys.stdout/stderr 的输出重定向到 logger 的代理类
    """
    def __init__(self, logger, level):
        self.logger = logger
        self.level = level

    def write(self, message):
        # 移除末尾换行符，因为 logger 打印时会自动添加
        msg = message.rstrip()
        if msg:
            for line in msg.splitlines():
                self.logger.log(self.level, line)

    def flush(self):
        # 满足流协议要求
        pass


def setup_logging(log_file, project_name):
    logging_config = {
        'version': 1,
        'formatters': {
            'default': {
                'format': f'%(asctime)s - %(name)s -{project_name} - %(levelname)s - %(message)s',
            },
        },
        'handlers': {
            'file': {
                'class': 'logging.FileHandler',
                'filename': log_file,
                'formatter': 'default',
                'level': 'DEBUG'
            },
            'console': {
                'class': 'logging.StreamHandler',
                # 关键：必须指向物理原始终端，防止重定向死循环
                'stream': 'ext://sys.__stdout__',
                'formatter': 'default',
                'level': 'DEBUG'
            },
        },
        'root': {
            'level': 'DEBUG',
            'handlers': ['file', 'console'],
        },
    }
    logging.config.dictConfig(logging_config)


def log_the_dockerfile(dockerfile_path, version, history_dir):
    dockerfile_version_name = os.path.basename(dockerfile_path)+ '-v' + str(version)
    dockerfile_version_path = os.path.join(history_dir, dockerfile_version_name)
    with open(dockerfile_path, 'r') as f:
        content = f.read()
    with open(dockerfile_version_path, 'w') as f:
        f.write(content)

def log_the_error_message(error_message, version, history_dir):
    error_message_version_name = "error_message"+ '-v' + str(version)
    error_message_version_path = os.path.join(history_dir, error_message_version_name)
    with open(error_message_version_path, 'w') as f:
        f.write(error_message)

def log_the_reasoning(reasoning_content, version, history_dir):
    if not reasoning_content:
        return
    reasoning_filename = f"reasoning-v{version}.txt"
    reasoning_path = os.path.join(history_dir, reasoning_filename)
    with open(reasoning_path, 'w', encoding='utf-8') as f:
        f.write("--- DEEPSEEK REASONER THINKING PROCESS ---\n")
        f.write(reasoning_content)
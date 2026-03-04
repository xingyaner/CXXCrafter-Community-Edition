import os

def _ensure_dir(path: str) -> str:
    """确保目录存在并返回绝对路径"""
    os.makedirs(path, exist_ok=True)
    return os.path.abspath(path)

def get_base_dir() -> str:
    """
    重写逻辑：将基准目录从家目录(~)移至项目根目录
    """
    # 1. 获取当前 init.py 的绝对路径
    # 路径为: .../CXXCrafter-Community-Edition/src/cxxcrafter/init.py
    current_file_path = os.path.abspath(__file__)
    
    # 2. 向上回溯两级到达项目根目录 CXXCrafter-Community-Edition
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file_path)))
    
    # 3. 在根目录下创建 .cxxcrafter 隐藏文件夹
    base_path = os.path.join(project_root, ".cxxcrafter")
    return _ensure_dir(base_path)

def get_log_dir() -> str:
    return _ensure_dir(os.path.join(get_base_dir(), "logs"))

def get_playground_dir() -> str:
    return _ensure_dir(os.path.join(get_base_dir(), "dockerfile_playground"))

def get_solution_base_dir() -> str:
    return _ensure_dir(os.path.join(get_base_dir(), "build_solution_base"))

def ensure_all_directories_exist():
    """初始化所有必需的子目录"""
    get_log_dir()
    get_playground_dir()
    get_solution_base_dir()

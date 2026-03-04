from .dockerfile_template import dockerfile_template


def get_initial_prompt(project_name, user_intention, environment_requirement, dependency, docs):
    """
    [Baseline 改写] 注入 OSS-Fuzz 元数据，并将任务定义为修复现有配置
    """
    # 从 user_intention (即 project_info) 提取信息
    p_info = user_intention
    base_image = p_info.get('base_image_digest', '')
    sanitizer = p_info.get('sanitizer', 'address')
    engine = p_info.get('engine', 'libfuzzer')
    
    # 获取原始报错日志的片段（如果可用）
    error_log_url = p_info.get('fuzzing_build_error_log', 'N/A')

    prompt_template = f"""
        You are a build engineering specialist. Your goal is to FIX the OSS-Fuzz build configuration for the project '{project_name}'.
        
        ENVIRONMENT CONSTRAINTS (MANDATORY):
        1. Base Image: You MUST use 'FROM gcr.io/oss-fuzz-base/base-builder@sha256:{base_image}'
        2. Build Target: Engine={engine}, Sanitizer={sanitizer}, Architecture={p_info.get('architecture')}
        
        TASK:
        Instead of creating a new project, you must FIX the existing Dockerfile and build.sh scripts to resolve the current build error.
        
        INPUT CONTEXT:
        - Build System: {environment_requirement}
        - Static Dependencies Found: {dependency}
        - Original Error Log Reference: {error_log_url}
        - Existing project documentation and hints: {docs}

        INSTRUCTIONS:
        1. Propose a complete Dockerfile that solves library missing issues or toolchain conflicts.
        2. Use the standard OSS-Fuzz project structure.
        3. If specific library versions are needed for {sanitizer}, ensure they are installed correctly.
        
        Follow this Dockerfile template structure:
        {dockerfile_template}
    """
    return prompt_template


prompt_template_for_modification = """
    Solve the problem according to the error message and modify the dockerfile.
    The dockerfile is:\n{last_dockerfile_content}\n
    The error message is:\n{feedback_message}\n
    
    Additionally, take note of the following items:
    1. If the error message indicates a network issue, do not make any modifications to the Dockerfile. 
    2. Please return a complete dockerfile rather than just providing advice.
    3. Try to keep the beginning of the Dockerfile unchanged and make minimal modifications towards the end of the file.
    4. In the dockerfile, commands must be executed one at a time.
    5. If some unnecessary modules, such as the testing module, are causing issues, they should be disabled through build options.
    6. If required packages, tools, or dependencies are missing, proceed with installing them rather than just verifying their presence.
    7. In case errors arise due to specific dependency versions, attempt to acquire and install the exact version of the software that is required.
    8. If a 404 error occurs while attempting to download a specific dependency version, verify the correctness of the download link and make any necessary corrections.
    """

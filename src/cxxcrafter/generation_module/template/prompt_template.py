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
You are currently in the iterative fix process. The previous build attempt FAILED.

[ACTUAL ERROR EVIDENCE]
Below are the LAST 400 LINES of the raw build log. This is the most important information to identify why the build failed (e.g., missing files, syntax errors, or linker issues):
---------- START OF LOG TAIL ----------
{log_tail}
---------- END OF LOG TAIL ----------

[CURRENT CONTEXT]
- Last Dockerfile content:
{last_dockerfile_content}

- System Status Signal:
{feedback_message}

[STRICT RULES FOR MODIFICATION]
1. Analyze the log tail provided above to identify the EXACT cause of failure.
2. Return a complete, corrected Dockerfile block within ```Dockerfile ```.
3. Try to keep the beginning of the Dockerfile unchanged.
4. Commands must be executed one at a time.
5. If the log shows path issues (e.g., 'No such file or directory'), verify WORKDIR and COPY instructions.
6. Ensure all required build dependencies are installed.
"""
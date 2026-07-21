import os
import re
import logging

from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage, SystemMessage

from app.config.llm_config import LLMs, LLMCreator
from app.tools.word_tool import read_docx
from app.prompts.agent_prompt import (
    PLANNER_SYSTEM,
    CODER_SYSTEM,
    build_coder_prompt,
)
from app.api.schemas import CodeFile, CodeGenState, PlanResult
from app.config.settings import settings

MODULE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
CODE_FENCE_PATTERN = re.compile(r"^\s*```(?:python)?\s*\n(?P<code>.*)\n```\s*$", re.DOTALL | re.IGNORECASE)
PROHIBITED_CODE_PATTERN = re.compile(
    r"\b(?:TODO|FIXME)\b|\b(?:eval|exec)\s*\(",
    re.IGNORECASE,
)
QUALITY_WARNING_PATTERN = re.compile(r"\b(?:for demonstration|for simplicity|assume)\b", re.IGNORECASE)
PASS_PLACEHOLDER_PATTERN = re.compile(r"^\s*pass\s*(?:#.*)?$", re.MULTILINE)
logger = logging.getLogger(__name__)


# ── Graph 节点 ────────────────────────────────────────────────────

def planner_node(state: CodeGenState) -> dict:
    llm = LLMCreator.get_llm(LLMs.FLASH, schema=PlanResult)
    messages = [
        SystemMessage(content=PLANNER_SYSTEM),
        HumanMessage(content=f"软件说明书：\n\n{state.spec_text}"),
    ]
    result = llm.invoke(messages)
    modules = [m.model_dump() for m in result.modules]
    if len(modules) < 6 or len(modules) > settings.max_generated_files:
        raise ValueError(f"模块数量不合法：应为 6 至 {settings.max_generated_files} 个")
    names = [module["name"] for module in modules]
    if len(names) != len(set(names)) or any(not MODULE_NAME_PATTERN.fullmatch(name) for name in names):
        raise ValueError("模型返回了不合法或重复的模块文件名")
    if modules[0]["name"] != "shared_core":
        raise ValueError("项目规划的第一个模块必须是 shared_core")
    for index, module in enumerate(modules):
        invalid_dependencies = set(module.get("dependencies", [])) - set(names[:index])
        if module["name"] in module.get("dependencies", []) or invalid_dependencies:
            raise ValueError(f"模块 {module['name']} 的依赖声明不合法")
    print(f"[planner] 规划了 {len(modules)} 个模块:")
    for m in modules:
        print(f"  - {m['name']}: {m['description'][:60]}")
    return {
        "modules": modules,
        "current_idx": 0,
        "generated_code": {},
    }


def generate_code_node(state: CodeGenState) -> dict:
    idx = state.current_idx
    module = state.modules[idx]

    prompt = build_coder_prompt(
        module_name=module["name"],
        module_desc=module["description"],
        key_classes=module.get("key_classes", []),
        key_functions=module.get("key_functions", []),
        spec_text=state.spec_text,
        generated_code=state.generated_code,
        project_modules=state.modules,
    )

    code = _generate_valid_code(module["name"], prompt, state.generated_code)

    line_count = len(code.splitlines())
    print(f"[generate_code] {module['name']}.py - {line_count} 行")

    new_generated = {**state.generated_code, module["name"]: code}
    return {"generated_code": new_generated}


def _normalize_code(code: str) -> str:
    """兼容个别模型在结构化字段中仍包裹 Markdown 围栏的情况。"""
    code = code.strip()
    match = CODE_FENCE_PATTERN.match(code)
    return match.group("code").strip() if match else code


def _validate_code_quality(module_name: str, code: str) -> None:
    """执行提示词中可自动验证的代码质量约束。"""
    line_count = len(code.splitlines())
    logger.info(
        "模块 %s 生成 %s 行代码（目标约 %s 行）",
        module_name,
        line_count,
        settings.target_code_file_lines,
    )
    prohibited = PROHIBITED_CODE_PATTERN.search(code)
    if prohibited:
        raise ValueError(f"包含禁止的占位或不安全写法：{prohibited.group(0).strip()}")
    warning = QUALITY_WARNING_PATTERN.search(code) or PASS_PLACEHOLDER_PATTERN.search(code)
    if warning:
        logger.warning("模块 %s 包含建议移除的写法：%s", module_name, warning.group(0))
    if module_name != "shared_core" and re.search(
        r"\bdeclarative_base\s*\(|\b(?:\w+\s*=\s*)?create_engine\s*\(|\b(?:\w+\s*=\s*)?sessionmaker\s*\(",
        code,
    ):
        raise ValueError("业务模块不得自行创建 SQLAlchemy Base、engine 或 sessionmaker，应从 shared_core 导入")


def _generate_valid_code(module_name: str, prompt: str, generated_code: dict[str, str]) -> str:
    """使用结构化输出生成代码；语法失败时携带精确错误信息重试。"""
    expected_filename = f"{module_name}.py"
    llm = LLMCreator.get_llm(LLMs.FLASH, schema=CodeFile)
    current_prompt = prompt
    last_error: Exception | None = None

    for attempt in range(settings.code_repair_attempts + 1):
        result = llm.invoke([
            SystemMessage(content=CODER_SYSTEM),
            HumanMessage(content=current_prompt),
        ])
        if result.filename != expected_filename:
            raise ValueError(f"模型返回的文件名不匹配：期望 {expected_filename}，实际 {result.filename}")

        code = _normalize_code(result.content)
        if len(code) > settings.max_code_file_chars:
            raise ValueError(f"{expected_filename} 超过单文件大小限制")
        if sum(len(item) for item in generated_code.values()) + len(code) > settings.max_total_code_chars:
            raise ValueError("生成代码总量超过限制")
        try:
            compile(code, expected_filename, "exec")
            _validate_code_quality(module_name, code)
            return code
        except (SyntaxError, ValueError) as exc:
            last_error = exc
            if isinstance(exc, SyntaxError):
                detail = f"{exc.msg}；第 {exc.lineno} 行、第 {exc.offset} 列；错误文本：{exc.text or ''}"
            else:
                detail = str(exc)
            logger.warning("模块 %s 第 %s 次质量校验失败：%s", expected_filename, attempt + 1, detail)
            if attempt >= settings.code_repair_attempts:
                break
            current_prompt = (
                f"请修复下面 {expected_filename} 的代码质量问题，并以 JSON 对象通过结构化输出返回同名文件的完整源码。"
                "JSON 必须包含 filename 和 content；content 只能含 Python 源码，不要 Markdown 或解释。\n"
                f"错误详情：{detail}\n\n"
                f"待修复源码：\n{code}"
            )

    assert last_error is not None
    raise ValueError(
        f"{expected_filename} 经过 {settings.code_repair_attempts} 次修复后仍未通过质量校验：{last_error}"
    )


def _total_code_lines(generated_code: dict[str, str]) -> int:
    return sum(len(code.splitlines()) for code in generated_code.values())


def _expand_module(module_name: str, code: str, missing_lines: int) -> str:
    """要求模型保留原代码并补充真实业务能力，以满足项目总行数要求。"""
    expected_filename = f"{module_name}.py"
    target_addition = min(max(missing_lines, 100), 500)
    prompt = f"""请扩展 {expected_filename}，以补充真实、与该模块职责相关的业务能力。

必须保留现有公开类、函数、签名和已有逻辑；新增约 {target_addition} 行有意义的代码，例如校验、查询、错误处理、业务服务或导出能力。不得复制代码凑行数，不得使用 TODO、pass 占位、eval 或 exec。

请以 JSON 对象通过结构化输出返回同名文件的完整源码。JSON 必须包含 filename 和 content；content 只能包含 Python 源码。

现有源码：
{code}
"""
    llm = LLMCreator.get_llm(LLMs.FLASH, schema=CodeFile)
    result = llm.invoke([SystemMessage(content=CODER_SYSTEM), HumanMessage(content=prompt)])
    if result.filename != expected_filename:
        raise ValueError(f"扩写时模型返回的文件名不匹配：期望 {expected_filename}，实际 {result.filename}")
    expanded = _normalize_code(result.content)
    if len(expanded) > settings.max_code_file_chars:
        raise ValueError(f"扩写后的 {expected_filename} 超过单文件大小限制")
    compile(expanded, expected_filename, "exec")
    _validate_code_quality(module_name, expanded)
    if len(expanded.splitlines()) <= len(code.splitlines()):
        raise ValueError(f"{expected_filename} 扩写后未增加有效代码行")
    return expanded


def _ensure_total_code_lines(state: dict) -> dict[str, str]:
    """在模块生成后补充最短模块，确保项目达到最低总代码行数。"""
    generated_code = dict(state["generated_code"])
    expansion_attempts = 0
    while _total_code_lines(generated_code) < settings.min_total_code_lines:
        if expansion_attempts >= settings.max_total_expansion_attempts:
            raise ValueError(
                f"项目总代码行数仍为 {_total_code_lines(generated_code)}，"
                f"已达到最大扩写次数 {settings.max_total_expansion_attempts}"
            )
        module_name = min(generated_code, key=lambda name: len(generated_code[name].splitlines()))
        before_lines = _total_code_lines(generated_code)
        generated_code[module_name] = _expand_module(
            module_name,
            generated_code[module_name],
            settings.min_total_code_lines - before_lines,
        )
        after_lines = _total_code_lines(generated_code)
        logger.info("扩写 %s：项目总行数 %s → %s", module_name, before_lines, after_lines)
        if after_lines <= before_lines:
            raise ValueError("扩写未增加项目总代码行数")
        expansion_attempts += 1
    return generated_code


def write_file_node(state: CodeGenState) -> dict:
    idx = state.current_idx
    module = state.modules[idx]
    code = state.generated_code[module["name"]]

    if not MODULE_NAME_PATTERN.fullmatch(module["name"]):
        raise ValueError("拒绝写入不合法的模块文件名")

    file_path = os.path.join(state.output_dir, f"{module['name']}.py")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(code)

    print(f"[write_file] {file_path}")
    return {
        "file_list": [file_path],
        "current_idx": idx + 1,
    }


def should_continue(state: CodeGenState) -> str:
    if state.current_idx < len(state.modules):
        return "generate_code"
    return "end"


# ── Graph 构建 ────────────────────────────────────────────────────

def _build_graph():
    graph = StateGraph(CodeGenState)
    graph.add_node("planner", planner_node)
    graph.add_node("generate_code", generate_code_node)
    graph.add_node("write_file", write_file_node)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "generate_code")
    graph.add_edge("generate_code", "write_file")
    graph.add_conditional_edges(
        "write_file",
        should_continue,
        {"generate_code": "generate_code", "end": END},
    )

    return graph.compile()


# ── 公共 API ──────────────────────────────────────────────────────

def code_generation_workflow(spec_path: str, output_dir: str) -> list[str]:
    """
    从软件说明书生成多个 Python 模块文件。

    Args:
        spec_path: 软件说明书.docx 路径
        output_dir: py 文件输出目录

    Returns:
        生成的文件路径列表
    """
    spec_text = read_docx(spec_path)
    os.makedirs(output_dir, exist_ok=True)

    app = _build_graph()

    initial_state = {
        "spec_text": spec_text,
        "output_dir": output_dir,
        "modules": [],
        "current_idx": 0,
        "generated_code": {},
        "file_list": [],
    }

    final_state = app.invoke(initial_state, {"recursion_limit": 50})
    generated_code = _ensure_total_code_lines(final_state)
    if generated_code != final_state["generated_code"]:
        for module_name, code in generated_code.items():
            file_path = os.path.join(output_dir, f"{module_name}.py")
            with open(file_path, "w", encoding="utf-8") as file:
                file.write(code)
    logger.info("项目代码总行数：%s", _total_code_lines(generated_code))
    return final_state["file_list"]


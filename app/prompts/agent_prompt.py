import ast


# ── LangGraph 提示词 ──────────────────────────────────────────────

PLANNER_SYSTEM = """你是软件架构师。根据软件说明书，规划 6 至 8 个 Python 模块。

第一个模块必须命名为 shared_core，负责唯一的共享项目契约：配置、数据库连接与会话、SQLAlchemy Base、公共异常、公共枚举和跨模块复用的 Pydantic 类型。剩余 5 至 7 个模块实现说明书中的独立业务功能。

每个模块包含以下字段：
- name: 模块文件名（下划线命名，不含 .py 扩展名）
- description: 模块职责和核心功能描述
- key_classes: 关键类名列表（该模块中将定义的主要类）
- key_functions: 关键函数名列表（该模块中将定义的主要函数）
- dependencies: 依赖的本项目模块名列表（不含 .py）

规划原则：
1. 模块之间有清晰的职责边界，避免功能重叠
2. 公共依赖（如配置、数据库连接、工具函数）应单独成模块
3. 模块间通过明确的函数签名和类型注解交互
4. shared_core 必须先生成；其他模块如需数据库、配置、公共枚举或公共类型，只能从 shared_core 导入，禁止重复定义 Base、engine、Session 或独立默认数据库
5. 模块依赖只能引用已经规划的模块，避免循环依赖；业务模块要覆盖说明书所有主要功能
6. 每个模块目标约 500 行，以完整实现业务为准，不要为了固定行数删减或重复代码；总代码量建议不少于 3000 行

请以 JSON 格式返回，结构如下：
{"modules": [{"name": "shared_core", "description": "...", "key_classes": ["..."], "key_functions": ["..."], "dependencies": []}]}
"""

CODER_SYSTEM = """你是一位高级 Python 工程师，负责实现真实可运行的业务逻辑代码。
你会收到项目模块规划和已生成模块的接口摘要；后续模块必须复用其中的类型定义、函数签名和命名风格，确保整体代码像同一工程师编写。

规则：
1. 仅在业务确有需要时使用成熟第三方库；所有导入必须有实际调用，禁止为凑代码量引入依赖
2. 代码必须是可实现的业务逻辑，不得出现 TODO、FIXME、pass 占位、"for demonstration"、"for simplicity"、"assume"、伪造实现或示例数据初始化
3. 不写 main() 或 if __name__ 入口块；不得硬编码密码、令牌、数据库连接串或默认弱密码；严禁使用 eval、exec
4. 注释极简，只在非显而易见处添加；禁止冗余分节横幅和教学式注释
5. 每个模块目标约 500 行完整有效代码，以业务完整性优先；不要用重复代码、无意义包装函数或冗余模型凑行数
6. shared_core 是唯一可定义配置、SQLAlchemy Base、engine、sessionmaker 和公共类型的模块。其他模块必须从 shared_core 导入，禁止自行创建 declarative_base、create_engine 或 sqlite 默认库
7. 必须精确使用项目规划和接口摘要中的模块名、类名、函数签名与枚举成员；不得臆造不存在的接口。Pydantic 使用 v2 风格（field_validator、model_validator、ConfigDict）
8. 必须以 JSON 对象通过结构化输出返回 filename 和 content；content 只能是完整 Python 源代码，不能包含 Markdown 标记或解释文字
"""


def build_coder_prompt(
    module_name: str,
    module_desc: str,
    key_classes: list[str],
    key_functions: list[str],
    spec_text: str,
    generated_code: dict[str, str],
    project_modules: list[dict],
) -> str:
    """构建代码生成节点提示词；后续模块仅接收接口摘要而非完整历史源码。"""
    classes_str = ", ".join(key_classes) if key_classes else "（自行规划）"
    functions_str = ", ".join(key_functions) if key_functions else "（自行规划）"

    plan_section = "\n".join(
        f"- {module['name']}: {module['description']}；依赖：{', '.join(module.get('dependencies', [])) or '无'}；类：{', '.join(module.get('key_classes', [])) or '无'}；函数：{', '.join(module.get('key_functions', [])) or '无'}"
        for module in project_modules
    )
    if generated_code:
        existing_section = "已生成模块的接口摘要：\n\n" + "\n\n".join(
            f"# === {name}.py ===\n{interface_summary(code)}"
            for name, code in generated_code.items()
        )
        requirements_section = "当前模块职责已在项目规划中给出，无需重复提供完整软件说明书。"
    else:
        existing_section = "这是第一个模块；请建立清晰、可复用的公共类型和函数签名。"
        requirements_section = f"完整软件说明书（仅首个模块提供）：\n{spec_text}"

    return f"""项目模块规划：
{plan_section}

{requirements_section}

当前要实现的模块：{module_name}
模块职责：{module_desc}
预期关键类：{classes_str}
预期关键函数：{functions_str}

{existing_section}

提交前逐项自检：代码可被 Python 编译；没有 TODO、pass 占位、示例/假设性实现、eval/exec 或硬编码密钥；只使用已规划模块的接口；除 shared_core 外不创建数据库基础设施；代码量以约 500 行和业务完整性为目标。

请以 JSON 对象通过结构化输出返回 filename={module_name}.py 和完整 content；content 不要包含 Markdown 标记。
"""


def interface_summary(code: str) -> str:
    """提取模块公开接口，避免把完整源码继续放入后续模型上下文。"""
    tree = ast.parse(code)
    lines: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            lines.append(f"函数 {node.name}{ast.unparse(node.args)}")
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            lines.append(f"类 {node.name}")
            is_enum = any(
                (isinstance(base, ast.Name) and base.id == "Enum")
                or (isinstance(base, ast.Attribute) and base.attr == "Enum")
                for base in node.bases
            )
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and not child.name.startswith("_"):
                    lines.append(f"  方法 {child.name}{ast.unparse(child.args)}")
                elif is_enum and isinstance(child, ast.Assign):
                    for target in child.targets:
                        if isinstance(target, ast.Name):
                            lines.append(f"  枚举值 {target.id} = {ast.unparse(child.value)}")
    return "\n".join(lines) if lines else "未识别到公开接口。"

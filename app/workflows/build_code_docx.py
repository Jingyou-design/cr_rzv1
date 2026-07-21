import os
import zipfile

from app.tools.word_tool import concat_py_files, fill_new_content

def build(folder: str, order: dict | None = None) -> str:
    """构建软著代码文档。

    Args:
        folder: 包含生成代码和软著材料的目录。
        order: 可选拼接顺序，格式为 {"files": ["shared_core.py", ...]}。
            未列出的 Python 文件按文件名排序后追加。
    """
    folder = os.path.abspath(folder)
    script_path = os.path.abspath(__file__)

    # 1. 查找模板 docx（文件名含"软件代码"）
    candidates = [
        f for f in os.listdir(folder)
        if f.endswith('.docx') and not f.startswith('~$') and '软件代码' in f
    ]
    if not candidates:
        raise FileNotFoundError(f'在 {folder} 下未找到文件名含"软件代码"的 docx 模板')
    template_docx = os.path.join(folder, candidates[0])
    print(f'模板文档: {candidates[0]}')

    # 2. 输出目录：文件夹下新建 output
    output_dir = os.path.join(folder, 'output')
    os.makedirs(output_dir, exist_ok=True)
    output_docx = os.path.join(output_dir, '软件代码.docx')
    output_zip = os.path.join(output_dir, '软件代码.zip')

    # 3. 收集 py 文件（不递归子目录），排除本脚本
    py_files = []
    for f in sorted(os.listdir(folder)):
        if not f.endswith('.py'):
            continue
        full = os.path.join(folder, f)
        if os.path.isfile(full) and os.path.abspath(full) != script_path:
            py_files.append(full)

    print(f'找到 {len(py_files)} 个 py 文件')
    for p in py_files:
        print(f'  - {os.path.basename(p)}')

    if not py_files:
        raise FileNotFoundError("未找到可写入软件代码文档的 .py 文件")

    if order is not None:
        if not isinstance(order, dict) or not isinstance(order.get("files"), list):
            raise ValueError('order 必须是 {"files": ["文件名.py", ...]} 格式')
        if any(not isinstance(name, str) for name in order["files"]):
            raise ValueError("order.files 中的每一项都必须是文件名字符串")

    # 4. 拼接：按实际生成的文件名排序，避免耦合到某个具体项目的模块名单
    content = concat_py_files(py_files, order=order)
    print(f'拼接完成，内容长度 {len(content)} 字符')

    # 5. 清空模板并填入内容
    fill_new_content(template_docx, output_docx, content)
    print(f'已写入 {output_docx}')

    # 6. 压缩指定文件（软件代码.docx + 软件说明书.docx + 系统填报说明.txt）
    files_to_zip = [
        output_docx,
        os.path.join(folder, '软件说明书.docx'),
        os.path.join(folder, '系统填报说明.txt'),
    ]
    missing_files = [f for f in files_to_zip if not os.path.exists(f)]
    if missing_files:
        raise FileNotFoundError(
            "缺少打包材料：" + "、".join(os.path.basename(f) for f in missing_files)
        )
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in files_to_zip:
            zf.write(f, os.path.basename(f))
            print(f'  已打包 {os.path.basename(f)}')
    print(f'已压缩到 {output_zip}')
    return output_zip

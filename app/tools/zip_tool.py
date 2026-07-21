import os
from pathlib import Path
import zipfile


class ZipSecurityError(ValueError):
    """压缩包包含不安全或超出资源限制的内容。"""


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return (info.external_attr >> 16) & 0o170000 == 0o120000


def _validate_member_path(destination: Path, name: str) -> None:
    target = (destination / name).resolve()
    try:
        target.relative_to(destination)
    except ValueError as exc:
        raise ZipSecurityError(f"压缩包包含非法路径：{name}") from exc


def unzip(
    zip_path: str | os.PathLike,
    extract_to: str | os.PathLike,
    *,
    max_files: int = 100,
    max_uncompressed_bytes: int = 300 * 1024 * 1024,
    max_compression_ratio: int = 100,
) -> None:
    """安全解压 ZIP，拒绝路径穿越、符号链接和压缩炸弹。"""
    destination = Path(extract_to).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as archive:
        members = archive.infolist()
        if len(members) > max_files:
            raise ZipSecurityError(f"压缩包文件数量超过限制（最多 {max_files} 个）")

        total_size = 0
        for info in members:
            if _is_symlink(info):
                raise ZipSecurityError(f"压缩包包含符号链接：{info.filename}")
            _validate_member_path(destination, info.filename)
            total_size += info.file_size
            if total_size > max_uncompressed_bytes:
                raise ZipSecurityError("压缩包解压后的总大小超过限制")
            if info.compress_size and info.file_size / info.compress_size > max_compression_ratio:
                raise ZipSecurityError(f"压缩包压缩比异常：{info.filename}")

        for info in members:
            target = destination / info.filename
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, open(target, "wb") as output:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)


def zip_dir(dir_path, zip_path):
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(dir_path):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, dir_path)
                zf.write(file_path, arcname)

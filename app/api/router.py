"""软著代码生成 API 路由"""

import os
import uuid
import shutil
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import zipfile

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from app.config.settings import settings
from app.api.schemas import TaskStatus, GenerateResponse, TaskStatusResponse
from app.api.task_manager import task_manager
from app.tools.zip_tool import unzip, ZipSecurityError
from app.workflows.code_generation import code_generation_workflow
from app.workflows.build_code_docx import build

router = APIRouter(prefix="/cr_rz", tags=["软著代码生成"])
logger = logging.getLogger(__name__)
executor = ThreadPoolExecutor(max_workers=settings.generation_workers, thread_name_prefix="codegen")


def _safe_filename(filename: str | None) -> str:
    name = Path((filename or "").replace("\\", "/")).name
    if not name or name in {".", ".."} or not name.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="仅支持上传 ZIP 文件")
    return name


async def _save_upload(upload: UploadFile, destination: Path) -> None:
    total = 0
    try:
        with open(destination, "wb") as output:
            while chunk := await upload.read(1024 * 1024):
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="上传文件超过大小限制")
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()


@router.post("/generate", response_model=GenerateResponse)
async def generate(files: list[UploadFile] = File(...)):
    task_ids = []
    for f in files:
        original_name = _safe_filename(f.filename)
        task_id = uuid.uuid4().hex[:12]

        task_dir = settings.upload_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        zip_path = task_dir / "input.zip"
        await _save_upload(f, zip_path)
        task_manager.create(task_id, original_name)
        executor.submit(_run_pipeline, task_id, str(task_dir), zip_path.name)
        task_ids.append(task_id)

    return GenerateResponse(task_ids=task_ids, task_id=task_ids[0])


def _run_pipeline(task_id: str, task_dir: str, original_name: str):
    try:
        task_manager.update(task_id, status=TaskStatus.IN_PROGRESS, stage="extracting")

        # 1. 解压
        zip_path = os.path.join(task_dir, original_name)
        unzip(
            zip_path,
            task_dir,
            max_files=settings.max_zip_files,
            max_uncompressed_bytes=settings.max_zip_uncompressed_bytes,
            max_compression_ratio=settings.max_zip_compression_ratio,
        )
        os.remove(zip_path)

        # 2. 查找说明书
        spec_candidates = [
            f for f in os.listdir(task_dir)
            if f.endswith(".docx") and not f.startswith("~$") and "说明书" in f
        ]
        if not spec_candidates:
            raise FileNotFoundError("压缩包内未找到软件说明书.docx")
        spec_path = os.path.join(task_dir, spec_candidates[0])

        # 3. 生成代码
        task_manager.update(task_id, status=TaskStatus.IN_PROGRESS, stage="generating")
        code_generation_workflow(spec_path, task_dir)

        # 4. 构建 docx + zip
        task_manager.update(task_id, status=TaskStatus.IN_PROGRESS, stage="packaging")
        output_zip = build(task_dir)

        # 5. 复制到 outputs
        settings.output_dir.mkdir(parents=True, exist_ok=True)
        final_zip = settings.output_dir / f"{task_id}.zip"
        shutil.copy2(output_zip, final_zip)

        # 6. 清理 upload 工作目录
        shutil.rmtree(task_dir, ignore_errors=True)

        task_manager.update(
            task_id,
            status=TaskStatus.COMPLETED,
            output_zip=str(final_zip),
            stage="completed",
        )

    except (FileNotFoundError, ZipSecurityError, ValueError) as exc:
        logger.warning("任务 %s 处理失败：%s", task_id, exc)
        task_manager.update(task_id, status=TaskStatus.FAILED, error=str(exc), stage="failed")
        shutil.rmtree(task_dir, ignore_errors=True)
    except zipfile.BadZipFile:
        logger.warning("任务 %s 上传了无效 ZIP 文件", task_id)
        task_manager.update(task_id, status=TaskStatus.FAILED, error="压缩包格式无效", stage="failed")
        shutil.rmtree(task_dir, ignore_errors=True)
    except Exception:
        logger.exception("任务 %s 处理时出现未预期异常", task_id)
        task_manager.update(
            task_id,
            status=TaskStatus.FAILED,
            error="任务处理失败，请检查输入材料或联系管理员",
            stage="failed",
        )
        shutil.rmtree(task_dir, ignore_errors=True)


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_status(task_id: str):
    task = task_manager.get(task_id)
    if not task:
        return TaskStatusResponse(
            task_id=task_id, status=TaskStatus.FAILED, error="任务不存在"
        )
    return TaskStatusResponse(
        task_id=task_id,
        status=task.status,
        stage=task.stage,
        error=task.error,
    )


@router.get("/download/{task_id}")
async def download(task_id: str):
    task = task_manager.get(task_id)
    if not task or task.status != TaskStatus.COMPLETED:
        raise HTTPException(status_code=404, detail="文件不存在或任务未完成")
    zip_path = settings.output_dir / f"{task_id}.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(
        zip_path,
        filename=task.filename,
        media_type="application/zip",
    )

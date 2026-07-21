"""FastAPI 启动入口"""

import os

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config.settings import settings
from app.api.router import router

app = FastAPI(title=settings.app_name)

# 确保目录存在
os.makedirs(settings.upload_dir, exist_ok=True)
os.makedirs(settings.output_dir, exist_ok=True)

# 挂载静态目录
app.mount("/uploads", StaticFiles(directory=str(settings.upload_dir)), name="uploads")
app.mount("/outputs", StaticFiles(directory=str(settings.output_dir)), name="outputs")

# 挂载路由
app.include_router(router, prefix=f"/{settings.api_prefix}")


@app.get("/")
async def root():
    return FileResponse("static/index.html")

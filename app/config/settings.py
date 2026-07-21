from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings


ROOT_PATH = Path(__file__).parent.parent.parent
load_dotenv()


class Settings(BaseSettings):
    # 应用配置
    app_name: str = Field(default="软著代码生成系统", env="APP_NAME")
    api_prefix: str = Field(default="api", env="API_PREFIX")
    public_host: str = Field(default="0.0.0.0", env="PUBLIC_HOST")
    public_port: int = Field(default=8000, env="PUBLIC_PORT")
    llm_debug: bool = Field(default=False, env="LLM_DEBUG")
    generation_workers: int = Field(default=5, ge=1, env="GENERATION_WORKERS")
    max_upload_bytes: int = Field(default=100 * 1024 * 1024, gt=0, env="MAX_UPLOAD_BYTES")
    max_zip_files: int = Field(default=100, ge=1, env="MAX_ZIP_FILES")
    max_zip_uncompressed_bytes: int = Field(
        default=300 * 1024 * 1024, gt=0, env="MAX_ZIP_UNCOMPRESSED_BYTES"
    )
    max_zip_compression_ratio: int = Field(default=100, ge=1, env="MAX_ZIP_COMPRESSION_RATIO")
    max_generated_files: int = Field(default=8, ge=1, env="MAX_GENERATED_FILES")
    max_code_file_chars: int = Field(default=200_000, gt=0, env="MAX_CODE_FILE_CHARS")
    max_total_code_chars: int = Field(default=1_000_000, gt=0, env="MAX_TOTAL_CODE_CHARS")
    target_code_file_lines: int = Field(default=500, ge=1, env="TARGET_CODE_FILE_LINES")
    min_total_code_lines: int = Field(default=3000, ge=1, env="MIN_TOTAL_CODE_LINES")
    max_total_expansion_attempts: int = Field(default=12, ge=1, env="MAX_TOTAL_EXPANSION_ATTEMPTS")
    code_repair_attempts: int = Field(default=2, ge=0, le=5, env="CODE_REPAIR_ATTEMPTS")

    # API 密钥
    deepseek_api_key: str = Field(default="", env="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com/v1", env="DEEPSEEK_BASE_URL"
    )
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1", env="OPENAI_BASE_URL"
    )
    qwen_api_key: str = Field(default="", env="DASHSCOPE_API_KEY")
    siliconflow_api_key: str = Field(default="", env="SILICONFLOW_API_KEY")
    siliconflow_base_url: str = Field(
        default="https://api.siliconflow.cn/v1", env="SILICONFLOW_BASE_URL"
    )

    # 服务配置
    mineru_url: str = Field(default="https://mineru.net", env="MINERU_URL")
    mineru_token: str = Field(default="", env="MINERU_TOKEN")
    callback_url: str = Field(
        default="http://localhost:8080/callback", env="CALLBACK_URL"
    )

    # 路径配置
    upload_dir: Path = Field(default=ROOT_PATH / "uploads", env="UPLOAD_DIR")
    output_dir: Path = Field(default=ROOT_PATH / "outputs", env="OUTPUT_DIR")
    temp_dir: Path = Field(default=ROOT_PATH / "temp", env="TEMP_DIR")
    template_dir: Path = Field(default=ROOT_PATH / "template", env="TEMPLATE_DIR")

    @property
    def docx_template_path(self) -> Path:
        return self.template_dir / "docx_template.docx"

    @property
    def output_url(self) -> str:
        return f"http://{self.public_host}:{self.public_port}/{self.api_prefix}/files"


settings = Settings()

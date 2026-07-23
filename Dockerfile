# 使用 Ubuntu 24.04 作为基础镜像
FROM ubuntu:24.04

# 设置环境变量，避免交互式安装
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

# 更换国内镜像源加速下载
RUN sed -i 's/archive.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list.d/ubuntu.sources \
    && sed -i 's/security.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list.d/ubuntu.sources

# 更新 apt 包列表并安装必要的包（Python 3.12 + pandoc）
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    git \
    build-essential \
    ca-certificates \
    gnupg \
    lsb-release \
    software-properties-common \
    python3 \
    python3-pip \
    pandoc \
    && rm -rf /var/lib/apt/lists/*

# 验证 Python 安装
RUN python3 --version && pip3 --version

# 配置 pip 使用国内镜像源
RUN pip3 config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple/ \
    && pip3 config set global.trusted-host pypi.tuna.tsinghua.edu.cn

# 设置工作目录
WORKDIR /app

# 先复制 requirements.txt 安装依赖
COPY requirements.txt .

# 安装 Python 依赖
RUN pip3 install -r requirements.txt --break-system-packages --ignore-installed PyJWT

# 最后复制整个项目目录
COPY . .

# 暴露端口
EXPOSE 8003

# 启动服务
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]

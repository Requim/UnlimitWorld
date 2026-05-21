# 天道不正经 — Python 后端容器
FROM python:3.11-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 源码 → server/ 子目录，保持 import 路径 server.xxx 可用
COPY . server/

# 暴露端口
EXPOSE 8000

# 启动命令（WORKDIR /app，Python 自动发现 server 包）
CMD ["python", "-m", "uvicorn", "server.interface.app:app", "--host", "0.0.0.0", "--port", "8000"]

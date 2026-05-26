# Tiandao FastAPI backend container
FROM python:3.11-slim

WORKDIR /app

ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    PIP_TRUSTED_HOST=mirrors.aliyun.com

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Keep source under server/ so imports like server.xxx work.
COPY . server/

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "server.interface.app:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CATENARY_STORE=/data/spans.json

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY wsgi.py ./

# 具名几何档持久化目录（可挂卷覆盖）
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8080

# 只做柔索悬链几何标定，负载很轻，Flask 内建线程化服务器即可
CMD ["python", "wsgi.py"]

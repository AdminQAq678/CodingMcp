FROM python:3.11-slim

WORKDIR /app

# 安装依赖
RUN pip install --no-cache-dir aiohttp

# 复制代码
COPY server.py server_http.py ./

# 默认启动 HTTP 模式
EXPOSE 8080
ENTRYPOINT ["python3", "server_http.py"]

# 默认以 /workspace 为根目录
CMD ["/workspace"]

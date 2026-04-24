# Repository MCP Server

代码仓库 MCP 服务器，提供文件读写、搜索、目录操作等能力。

## 功能

| 工具 | 功能 |
|------|------|
| read_file | 读取文件内容，支持分页 |
| write_file | 写入或追加文件内容 |
| search_files | 搜索文件内容 (正则表达式) |
| list_directory | 列出目录内容 |
| create_directory | 创建目录 |
| file_exists | 检查文件是否存在 |
| get_file_info | 获取文件信息 |
| delete_file | 删除文件或目录 |
| glob_files | 查找匹配模式的文件 |
| set_root_path | 切换工作目录 |
| get_current_path | 获取当前工作目录 |
| list_allowed_paths | 列出允许访问的路径 |

## 依赖

### 必需

- **Python 3.9+**

### HTTP/SSE 模式依赖

```
aiohttp>=3.9.0
```

安装依赖:

```bash
pip install -r requirements.txt
```

## 启动方式

### 1. Stdio 模式 (无依赖)

```bash
# 指定根目录
python3 server.py /path/to/your/repo

# 或使用当前目录
python3 server.py .
```

### 2. HTTP 模式

```bash
# 安装依赖
pip install -r requirements.txt

# 启动 HTTP 服务器
python3 server_http.py /path/to/your/repo

# 默认端口 8080，可通过环境变量修改
PORT=9000 python3 server_http.py /path/to/your/repo
```

### 3. SSE 模式

SSE 模式支持长连接推送:

```bash
python3 server_http.py /path/to/your/repo
# SSE 端点: GET /sse
# 消息端点: POST /sse/message
```

## API 端点

### HTTP 模式

```bash
# 列出工具
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# 调用工具
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "read_file",
      "arguments": {"path": "server.py", "limit": 10}
    }
  }'

# 健康检查
curl http://localhost:8080/health
```

### SSE 模式

```javascript
// 连接 SSE
const eventSource = new EventSource('http://localhost:8080/sse');

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Received:', data);
};

// 发送消息
await fetch('http://localhost:8080/sse/message', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    jsonrpc: '2.0',
    id: 1,
    method: 'tools/call',
    params: {
      name: 'list_directory',
      arguments: {path: '.'}
    }
  })
});
```

## Docker 部署

```bash
# 构建镜像
docker build -t repository-mcp .

# 运行 (HTTP 模式)
docker run -p 8080:8080 -v /your/repo:/workspace repository-mcp /workspace

# 或使用 docker-compose
docker-compose up -d
```

## 配置到 Claude/Cursor

### Stdio 模式

```json
{
  "mcpServers": {
    "repository": {
      "command": "python3",
      "args": ["/path/to/server.py", "/path/to/your/repo"]
    }
  }
}
```

### HTTP 模式

```json
{
  "mcpServers": {
    "repository": {
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

## 云部署

### Railway/Render

1. 推送到 GitHub
2. 在 Railway/Render 上选择 Python 服务
3. 设置启动命令: `python3 server_http.py /workspace`
4. 挂载持久化存储或绑定 Git 仓库

### Vercel (Serverless)

创建 `vercel.json`:

```json
{
  "builds": [{
    "src": "server_http.py",
    "use": "@vercel/python"
  }],
  "routes": [{
    "src": "/(.*)",
    "dest": "server_http.py"
  }]
}
```

### 自定义域名 + HTTPS

使用 Nginx 反向代理:

```nginx
server {
    listen 443 ssl;
    server_name mcp.yourdomain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://localhost:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

## 安全

- 所有文件操作限制在指定根目录内 (目录遍历攻击防护)
- 生产环境建议配合 HTTPS 使用
- 可通过环境变量配置端口和根路径

#!/usr/bin/env python3
"""
Repository MCP Server - 支持 HTTP/SSE 模式
需要 aiohttp: pip install aiohttp
"""

import os
import sys
import json
import asyncio
from pathlib import Path
from aiohttp import web
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MCPServerHTTP:
    """MCP HTTP/SSE 服务器"""
    
    def __init__(self, root_path: str):
        self.root_path = Path(root_path)
        self.sessions = {}  # session_id -> mcp instance
        self.app = None
    
    def create_mcp(self):
        """创建 MCP 实例 (延迟导入避免依赖)"""
        from server import RepositoryMCP, MCPRequest, MCPResponse
        return RepositoryMCP(self.root_path), MCPRequest, MCPResponse
    
    async def handle_initialize(self, mcp, data):
        """处理初始化"""
        MCPRequest = mcp.__class__.__module__
        from server import MCPRequest as MCPR
        from server import MCPResponse as MCPRsp
        
        request = MCPR(data)
        response = mcp.handle_request(request)
        return response.to_dict()
    
    async def handle_json_rpc(self, mcp, data):
        """处理 JSON-RPC 请求"""
        from server import MCPRequest, MCPResponse
        
        request = MCPRequest(data)
        response = mcp.handle_request(request)
        return response.to_dict()


# ==================== HTTP 模式 ====================

async def http_handle_mcp(request):
    """HTTP 模式 - 同步请求/响应"""
    mcp_server = request.app['mcp_server']
    mcp, MCPR, MCPRsp = mcp_server.create_mcp()
    
    data = await request.json()
    logger.info(f"HTTP request: {data.get('method')}")
    
    response = mcp.handle_request(MCPR(data))
    return web.json_response(response.to_dict())


# ==================== SSE 模式 ====================

class SSESession:
    """SSE 会话"""
    def __init__(self, session_id, mcp_server):
        self.session_id = session_id
        self.mcp_server = mcp_server
        self.mcp, self.MCPR, self.MCPRsp = mcp_server.create_mcp()
        self.queue = asyncio.Queue()
    
    async def send(self, data):
        """发送消息到客户端"""
        await self.queue.put(data)


async def sse_handle_connect(request):
    """SSE 模式 - 建立连接"""
    mcp_server = request.app['mcp_server']
    
    # 创建会话
    import uuid
    session_id = str(uuid.uuid4())
    session = SSESession(session_id, mcp_server)
    mcp_server.sessions[session_id] = session
    
    logger.info(f"SSE session connected: {session_id}")
    
    # 设置 CORS 头
    response = web.StreamResponse(
        status=200,
        headers={
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*',
        }
    )
    await response.prepare(request)
    
    async def send_sse(data):
        """发送 SSE 消息"""
        if isinstance(data, dict):
            data = json.dumps(data)
        response.write(f"data: {data}\n\n".encode())
        await response.drain()
    
    # 发送初始化消息
    await send_sse({"type": "connected", "session_id": session_id})
    
    # 保持连接，监听队列
    try:
        while True:
            try:
                msg = await asyncio.wait_for(session.queue.get(), timeout=30)
                await send_sse(msg)
            except asyncio.TimeoutError:
                # 发送心跳
                await send_sse({"type": "ping"})
    except (asyncio.CancelledError, ConnectionResetError):
        pass
    finally:
        del mcp_server.sessions[session_id]
        logger.info(f"SSE session disconnected: {session_id}")
    
    return response


async def sse_handle_message(request):
    """SSE 模式 - 发送消息"""
    mcp_server = request.app['mcp_server']
    data = await request.json()
    
    session_id = data.get("session_id")
    if not session_id or session_id not in mcp_server.sessions:
        return web.json_response(
            {"error": {"code": -32000, "message": "Invalid session"}},
            status=400
        )
    
    session = mcp_server.sessions[session_id]
    logger.info(f"SSE message: {data.get('method')} for session {session_id}")
    
    # 处理请求
    response = session.mcp.handle_request(session.MCPR(data))
    result = response.to_dict()
    
    # 直接返回响应 (同步模式)
    return web.json_response(result)


# ==================== 主程序 ====================

def create_app(root_path: str):
    """创建应用"""
    mcp_server = MCPServerHTTP(root_path)
    
    app = web.Application()
    app['mcp_server'] = mcp_server
    
    # HTTP 模式端点
    app.router.add_post('/mcp', http_handle_mcp)
    
    # SSE 模式端点
    app.router.add_get('/sse', sse_handle_connect)
    app.router.add_post('/sse/message', sse_handle_message)
    
    # 健康检查
    app.router.add_get('/health', lambda r: web.json_response({
        "status": "ok",
        "root_path": str(mcp_server.root_path),
        "sessions": len(mcp_server.sessions)
    }))
    app.router.add_get('/', lambda r: web.json_response({
        "name": "repository-mcp",
        "version": "1.0.0",
        "endpoints": {
            "http": "/mcp",
            "sse_connect": "/sse",
            "sse_message": "/sse/message",
            "health": "/health"
        }
    }))
    
    return app


def main():
    root_path = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    port = int(os.environ.get('PORT', 8080))
    
    print(f"Repository MCP Server")
    print(f"  Root path: {root_path}")
    print(f"  Port: {port}")
    print(f"  Endpoints:")
    print(f"    HTTP:  POST http://localhost:{port}/mcp")
    print(f"    SSE:   GET  http://localhost:{port}/sse")
    print(f"    Health: GET http://localhost:{port}/health")
    
    app = create_app(root_path)
    web.run_app(app, host='0.0.0.0', port=port, print=None)


if __name__ == "__main__":
    main()

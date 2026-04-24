#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Repository MCP Server - 纯标准库实现
无需外部依赖，直接使用 Python 标准库
"""

import os
import sys
import json
import re
from pathlib import Path
from typing import Any, Optional, Dict, List, Union
import threading


class MCPTool:
    """MCP 工具定义"""
    def __init__(self, name: str, description: str, input_schema: dict):
        self.name = name
        self.description = description
        self.input_schema = input_schema


class MCPRequest:
    """MCP 请求"""
    def __init__(self, json_data: dict):
        self.jsonrpc = json_data.get("jsonrpc", "2.0")
        self.id = json_data.get("id")
        self.method = json_data.get("method")
        self.params = json_data.get("params", {})


class MCPResponse:
    """MCP 响应"""
    def __init__(self, id, result=None, error=None):
        self.jsonrpc = "2.0"
        self.id = id
        self.result = result
        self.error = error
    
    def to_dict(self) -> dict:
        if self.error:
            return {
                "jsonrpc": self.jsonrpc,
                "id": self.id,
                "error": self.error
            }
        return {
            "jsonrpc": self.jsonrpc,
            "id": self.id,
            "result": self.result
        }


class RepositoryMCP:
    """代码仓库 MCP 服务器"""
    
    def __init__(self, root_path: Optional[str] = None):
        self.root_path = Path(root_path) if root_path else Path.cwd()
        self.tools: Dict[str, callable] = {}
        self._register_tools()
    
    def _register_tools(self):
        """注册所有工具"""
        self.tools = {
            "read_file": {
                "fn": self._read_file,
                "description": "读取文件内容，支持分页",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "文件路径"},
                        "offset": {"type": "integer", "description": "起始行号 (1-indexed)", "default": 1},
                        "limit": {"type": "integer", "description": "最大行数", "default": 500}
                    },
                    "required": ["path"]
                }
            },
            "write_file": {
                "fn": self._write_file,
                "description": "写入或追加文件内容",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "文件路径"},
                        "content": {"type": "string", "description": "文件内容"},
                        "mode": {"type": "string", "description": "模式: overwrite 或 append", "default": "overwrite"}
                    },
                    "required": ["path", "content"]
                }
            },
            "search_files": {
                "fn": self._search_files,
                "description": "搜索文件内容 (正则表达式)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "搜索模式 (正则)"},
                        "path": {"type": "string", "description": "搜索路径", "default": "."},
                        "file_glob": {"type": "string", "description": "文件过滤 (如 *.py)", "default": None},
                        "limit": {"type": "integer", "description": "最大结果数", "default": 50}
                    },
                    "required": ["pattern"]
                }
            },
            "list_directory": {
                "fn": self._list_directory,
                "description": "列出目录内容",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "目录路径", "default": "."},
                        "include_hidden": {"type": "boolean", "description": "包含隐藏文件", "default": False}
                    }
                }
            },
            "create_directory": {
                "fn": self._create_directory,
                "description": "创建目录",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "目录路径"}
                    },
                    "required": ["path"]
                }
            },
            "file_exists": {
                "fn": self._file_exists,
                "description": "检查文件是否存在",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "文件路径"}
                    },
                    "required": ["path"]
                }
            },
            "get_file_info": {
                "fn": self._get_file_info,
                "description": "获取文件信息",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "文件路径"}
                    },
                    "required": ["path"]
                }
            },
            "delete_file": {
                "fn": self._delete_file,
                "description": "删除文件或目录",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "文件路径"}
                    },
                    "required": ["path"]
                }
            },
            "glob_files": {
                "fn": self._glob_files,
                "description": "查找匹配模式的文件",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Glob 模式 (如 **/*.py)"},
                        "path": {"type": "string", "description": "搜索路径", "default": "."}
                    },
                    "required": ["pattern"]
                }
            },
            "set_root_path": {
                "fn": self._set_root_path,
                "description": "切换当前工作目录到指定项目路径",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "新的项目路径 (绝对路径或相对路径)"}
                    },
                    "required": ["path"]
                }
            },
            "get_current_path": {
                "fn": self._get_current_path,
                "description": "获取当前工作目录路径",
                "input_schema": {
                    "type": "object",
                    "properties": {}
                }
            },
            "list_allowed_paths": {
                "fn": self._list_allowed_paths,
                "description": "列出允许访问的路径 (仅当前根目录的上级目录)",
                "input_schema": {
                    "type": "object",
                    "properties": {}
                }
            }
        }
    
    def _resolve_path(self, path: str) -> Path:
        """解析相对路径"""
        p = Path(path)
        if p.is_absolute():
            return p
        return self.root_path / p
    
    def _safe_path(self, path: Path) -> bool:
        """检查路径是否在允许目录内"""
        try:
            resolved = path.resolve()
            root = self.root_path.resolve()
            return str(resolved).startswith(str(root))
        except:
            return False
    
    # === 工具实现 ===
    
    def _read_file(self, path: str, offset: int = 1, limit: int = 500) -> dict:
        """读取文件内容"""
        try:
            full_path = self._resolve_path(path)
            if not self._safe_path(full_path):
                return {"success": False, "error": "Path outside allowed directory"}
            
            if not full_path.exists():
                return {"success": False, "error": f"File not found: {path}"}
            
            if not full_path.is_file():
                return {"success": False, "error": f"Not a file: {path}"}
            
            with open(full_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            total_lines = len(lines)
            start = max(0, offset - 1)
            end = min(total_lines, start + limit)
            content = ''.join(lines[start:end])
            
            return {
                "success": True,
                "content": content,
                "total_lines": total_lines,
                "offset": offset,
                "limit": limit,
                "path": str(full_path.relative_to(self.root_path))
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _write_file(self, path: str, content: str, mode: str = "overwrite") -> dict:
        """写入文件"""
        try:
            full_path = self._resolve_path(path)
            if not self._safe_path(full_path):
                return {"success": False, "error": "Path outside allowed directory"}
            
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(full_path, 'a' if mode == "append" else 'w', encoding='utf-8') as f:
                f.write(content)
            
            return {
                "success": True,
                "path": str(full_path.relative_to(self.root_path)),
                "mode": mode
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _search_files(self, pattern: str, path: str = ".", file_glob: str = None, 
                      limit: int = 50) -> dict:
        """搜索文件内容"""
        try:
            search_path = self._resolve_path(path)
            if not self._safe_path(search_path):
                return {"success": False, "error": "Path outside allowed directory"}
            
            if not search_path.exists():
                return {"success": False, "error": f"Path not found: {path}"}
            
            matches = []
            regex = re.compile(pattern)
            
            for file_path in search_path.rglob(file_glob or "*"):
                if not file_path.is_file():
                    continue
                if file_path.stat().st_size > 1024 * 1024:  # 跳过 >1MB
                    continue
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                except:
                    continue
                
                for i, line in enumerate(lines, 1):
                    if regex.search(line):
                        matches.append({
                            "file": str(file_path.relative_to(self.root_path)),
                            "line": i,
                            "content": line.rstrip()
                        })
                        if len(matches) >= limit:
                            break
                if len(matches) >= limit:
                    break
            
            return {
                "success": True,
                "matches": matches,
                "total": len(matches),
                "pattern": pattern
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _list_directory(self, path: str = ".", include_hidden: bool = False) -> dict:
        """列出目录"""
        try:
            dir_path = self._resolve_path(path)
            if not self._safe_path(dir_path):
                return {"success": False, "error": "Path outside allowed directory"}
            
            if not dir_path.exists():
                return {"success": False, "error": f"Directory not found: {path}"}
            
            items = []
            for item in sorted(dir_path.iterdir()):
                if not include_hidden and item.name.startswith('.'):
                    continue
                items.append({
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "path": str(item.relative_to(self.root_path))
                })
            
            return {
                "success": True,
                "path": str(dir_path.relative_to(self.root_path)),
                "items": items,
                "total": len(items)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _create_directory(self, path: str) -> dict:
        """创建目录"""
        try:
            dir_path = self._resolve_path(path)
            if not self._safe_path(dir_path):
                return {"success": False, "error": "Path outside allowed directory"}
            
            dir_path.mkdir(parents=True, exist_ok=True)
            return {"success": True, "path": str(dir_path.relative_to(self.root_path))}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _file_exists(self, path: str) -> dict:
        """检查文件是否存在"""
        try:
            full_path = self._resolve_path(path)
            if not self._safe_path(full_path):
                return {"success": False, "error": "Path outside allowed directory"}
            
            return {
                "success": True,
                "exists": full_path.exists(),
                "is_file": full_path.is_file() if full_path.exists() else None,
                "is_dir": full_path.is_dir() if full_path.exists() else None,
                "path": str(full_path.relative_to(self.root_path))
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _get_file_info(self, path: str) -> dict:
        """获取文件信息"""
        try:
            full_path = self._resolve_path(path)
            if not self._safe_path(full_path):
                return {"success": False, "error": "Path outside allowed directory"}
            
            if not full_path.exists():
                return {"success": False, "error": f"File not found: {path}"}
            
            stat = full_path.stat()
            return {
                "success": True,
                "path": str(full_path.relative_to(self.root_path)),
                "name": full_path.name,
                "size": stat.st_size,
                "is_file": full_path.is_file(),
                "is_dir": full_path.is_dir(),
                "modified": stat.st_mtime,
                "created": stat.st_ctime
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _delete_file(self, path: str) -> dict:
        """删除文件"""
        try:
            full_path = self._resolve_path(path)
            if not self._safe_path(full_path):
                return {"success": False, "error": "Path outside allowed directory"}
            
            if not full_path.exists():
                return {"success": False, "error": f"Path not found: {path}"}
            
            if full_path.is_file():
                full_path.unlink()
            elif full_path.is_dir():
                import shutil
                shutil.rmtree(full_path)
            
            return {"success": True, "path": str(full_path.relative_to(self.root_path))}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _glob_files(self, pattern: str, path: str = ".") -> dict:
        """查找匹配的文件"""
        try:
            search_path = self._resolve_path(path)
            if not self._safe_path(search_path):
                return {"success": False, "error": "Path outside allowed directory"}
            
            files = []
            for p in search_path.glob(pattern):
                if p.is_file():
                    files.append(str(p.relative_to(self.root_path)))
            
            return {
                "success": True,
                "files": files,
                "total": len(files),
                "pattern": pattern
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _set_root_path(self, path: str) -> dict:
        """切换工作目录"""
        try:
            # 解析新路径
            new_path = Path(path)
            if not new_path.is_absolute():
                # 相对路径相对于当前根目录
                new_path = self.root_path / new_path
            new_path = new_path.resolve()
            
            # 检查目录是否存在
            if not new_path.exists():
                return {"success": False, "error": f"Directory does not exist: {path}"}
            
            if not new_path.is_dir():
                return {"success": False, "error": f"Not a directory: {path}"}
            
            # 切换目录
            old_path = self.root_path
            self.root_path = new_path
            
            return {
                "success": True,
                "old_path": str(old_path),
                "new_path": str(self.root_path)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _get_current_path(self) -> dict:
        """获取当前工作目录"""
        return {
            "success": True,
            "path": str(self.root_path),
            "absolute": str(self.root_path.resolve())
        }
    
    def _list_allowed_paths(self) -> dict:
        """列出允许访问的路径"""
        try:
            root = self.root_path.resolve()
            # 尝试获取上两级目录作为允许范围
            parent = root.parent
            grandparent = parent.parent
            
            paths = []
            for p in [root, parent, grandparent]:
                if p.exists():
                    paths.append({
                        "path": str(p),
                        "name": p.name,
                        "exists": True
                    })
            
            return {
                "success": True,
                "current": str(root),
                "allowed_paths": paths
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # === MCP 协议处理 ===
    
    def list_tools(self) -> List[dict]:
        """列出所有工具"""
        return [
            {
                "name": name,
                "description": info["description"],
                "inputSchema": info["input_schema"]
            }
            for name, info in self.tools.items()
        ]
    
    def call_tool(self, name: str, arguments: dict) -> dict:
        """调用工具"""
        if name not in self.tools:
            return {"success": False, "error": f"Unknown tool: {name}"}
        
        try:
            fn = self.tools[name]["fn"]
            # 过滤掉 None 值
            args = {k: v for k, v in arguments.items() if v is not None}
            return fn(**args)
        except TypeError as e:
            return {"success": False, "error": f"Invalid arguments: {e}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def handle_request(self, request: MCPRequest) -> MCPResponse:
        """处理 MCP 请求"""
        try:
            if request.method == "initialize":
                return MCPResponse(
                    id=request.id,
                    result={
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {
                            "name": "repository-server",
                            "version": "1.0.0"
                        },
                        "capabilities": {
                            "tools": {}
                        }
                    }
                )
            
            elif request.method == "tools/list":
                return MCPResponse(
                    id=request.id,
                    result={"tools": self.list_tools()}
                )
            
            elif request.method == "tools/call":
                params = request.params
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                result = self.call_tool(tool_name, arguments)
                return MCPResponse(
                    id=request.id,
                    result={
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result, ensure_ascii=False, indent=2)
                            }
                        ]
                    }
                )
            
            else:
                return MCPResponse(
                    id=request.id,
                    error={
                        "code": -32601,
                        "message": f"Method not found: {request.method}"
                    }
                )
        except Exception as e:
            return MCPResponse(
                id=request.id,
                error={
                    "code": -32603,
                    "message": str(e)
                }
            )


def main():
    """主入口 - Stdio 模式"""
    root_path = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    
    print(f"Repository MCP Server starting...", file=sys.stderr)
    print(f"Root path: {root_path}", file=sys.stderr)
    
    mcp = RepositoryMCP(root_path)
    
    # 读取模式
    read_buffer = ""
    
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            
            read_buffer += line
            
            # 尝试解析 JSON
            try:
                data = json.loads(read_buffer)
                read_buffer = ""
                
                request = MCPRequest(data)
                response = mcp.handle_request(request)
                
                # 输出响应
                print(json.dumps(response.to_dict(), ensure_ascii=False), flush=True)
                
            except json.JSONDecodeError:
                # 不完整，继续读取
                continue
                
        except EOFError:
            break
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()

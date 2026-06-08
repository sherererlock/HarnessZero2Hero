#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单的 HTTP ping 接口服务
提供 /ping 端点，返回 JSON 格式的响应。
"""

import json
import http.server
import socketserver
from typing import Dict, Any


class PingHandler(http.server.BaseHTTPRequestHandler):
    """处理 HTTP 请求的处理器"""

    def do_GET(self) -> None:
        """处理 GET 请求"""
        if self.path == "/ping":
            response: Dict[str, Any] = {
                "code": 200,
                "message": "pong"
            }
            self._send_json_response(response)
        else:
            response = {
                "code": 404,
                "message": "请求的路径不存在"
            }
            self._send_json_response(response, status_code=404)

    def _send_json_response(self, data: Dict[str, Any], status_code: int = 200) -> None:
        """发送 JSON 格式的响应"""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        response_json = json.dumps(data, ensure_ascii=False)
        self.wfile.write(response_json.encode("utf-8"))

    def log_message(self, format: str, *args) -> None:
        """自定义日志格式"""
        print(f"[{self.log_date_time_string()}] {format % args}")


def run_server(host: str = "0.0.0.0", port: int = 8080) -> None:
    """启动 HTTP 服务器"""
    with socketserver.TCPServer((host, port), PingHandler) as httpd:
        print(f"Ping 服务启动中，监听地址: http://{host}:{port}")
        print("按 Ctrl+C 停止服务")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n服务已停止")


if __name__ == "__main__":
    run_server()
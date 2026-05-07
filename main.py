# -*- coding: utf-8 -*-
"""
LangChainSkills FastAPI 服务

提供 Skills 智能体的 HTTP API 接口，支持流式响应
"""

import asyncio
import json
import logging
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Optional
from uuid import uuid4

import aiofiles
import uvicorn
from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest, start_http_server
from pydantic import BaseModel, Field

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent / "LangChainSkills"))

from agent import create_skill_agent
from config import load_config


# =================初始化配置和日志=================
def setup_logging():
    """初始化日志配置"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
        ]
    )


setup_logging()
logger = logging.getLogger(__name__)

# 加载配置
config_path = Path(__file__).parent / "LangChainSkills" / "config.yaml"
settings = load_config(config_path)

# =================路径配置=================
STATIC_DIR = Path(settings.static_dir)
IMG_DIR = STATIC_DIR / "img"

# 需要JSON输出的工具函数名集合
FUNCS_WITH_JSON_OUTPUT = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    try:
        yield
    except Exception as e:
        logger.exception(f"Error during application lifecycle: {e}")
        raise


# =================FastAPI 应用初始化=================
app = FastAPI(lifespan=lifespan, title="LangChainSkills API", version="1.0.0")
app_start_time = time.time()

# =================Prometheus 指标定义=================
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP Requests",
    ["method", "endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP Request Duration",
    ["method", "endpoint"]
)


# =================中间件=================
@app.middleware("http")
async def add_prometheus_metrics(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time

    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    REQUEST_LATENCY.labels(
        method=request.method,
        endpoint=request.url.path
    ).observe(process_time)

    return response


# =================后台服务=================
def start_metrics_server():
    """启动 Prometheus 指标服务器"""
    start_http_server(port=settings.metrics_port)
    logger.info(f"Prometheus metrics server started on port {settings.metrics_port}")


# =================路由：监控与健康=================
@app.get("/metrics", include_in_schema=False)
def metrics():
    """暴露 Prometheus 指标"""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
def health():
    """健康检查"""
    uptime = time.time() - app_start_time
    return {"status": "ok", "uptime_seconds": round(uptime, 2)}


# =================路由：静态文件=================
async def serve_file(file_path: Path, media_type: str):
    """通用文件服务助手"""
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    try:
        mode = 'r' if 'text' in media_type or media_type == "text/html" else 'rb'
        async with aiofiles.open(file_path, mode=mode) as f:
            content = await f.read()

        if mode == 'r':
            return HTMLResponse(content=content) if media_type == "text/html" else Response(content=content,
                                                                                            media_type=media_type)
        else:
            return Response(content=content, media_type=media_type)
    except Exception as e:
        logger.error(f"Error serving file {file_path}: {e}")
        raise HTTPException(status_code=500, detail="文件读取失败")


@app.get("/static/{path:path}")
async def serve_static(path: str):
    """服务静态文件 (HTML/CSS/JS)"""
    file_path = STATIC_DIR / path
    return await serve_file(file_path, media_type="text/html")


@app.get("/img/{path:path}")
async def serve_image(path: str):
    """服务图片文件"""
    file_path = IMG_DIR / path
    suffix = file_path.suffix.lower()
    media_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif",
        ".webp": "image/webp", ".svg": "image/svg+xml"
    }
    media_type = media_map.get(suffix, "application/octet-stream")
    return await serve_file(file_path, media_type=media_type)


# =================数据模型=================
class QueryRequest(BaseModel):
    session_id: Optional[str] = Field(default=None, description="Session ID")
    message: str = Field(..., description="User message")
    stream_mode: str = Field(default="MESSAGES", description="输出模式: MESSAGES=流式, UPDATES=步骤")


class StreamResponse(BaseModel):
    type: str
    event: str
    content: str = ""
    agent: str = ""
    data: Any = {}
    meta: Any = {}


# =================流式响应辅助函数=================
def create_sse_response(res: StreamResponse) -> str:
    """创建 SSE 格式的响应字符串"""
    return f"data: {res.model_dump_json()}\n\n"


def create_error_response(error_msg: str) -> str:
    """创建错误响应"""
    error_res = StreamResponse(type="error", event="system", content=error_msg, agent="system")
    return create_sse_response(error_res)


# =================核心逻辑辅助函数=================
def extract_common_response(graph_output: dict) -> dict:
    """提取非流式调用的标准响应"""
    try:
        last_msg = None
        for msg_block in reversed(graph_output):
            if "model" in msg_block and "messages" in msg_block["model"]:
                messages = msg_block["model"]["messages"]
                if messages:
                    last_msg = messages[-1]
                    break

        if not last_msg or not hasattr(last_msg, 'content'):
            raise ValueError("No valid model response found")

        answer = last_msg.content

        tool_content_list = []
        for msg_block in graph_output:
            if "tools" in msg_block and "messages" in msg_block["tools"]:
                tools_msgs = msg_block["tools"]["messages"]
                if tools_msgs:
                    raw_content = tools_msgs[0].content
                    try:
                        parsed = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
                        if isinstance(parsed, list):
                            tool_content_list = [item.get("content", str(item)) for item in parsed]
                        else:
                            tool_content_list = [str(parsed)]
                    except json.JSONDecodeError:
                        tool_content_list = [str(raw_content)]
                    break

        return {"answer": str(answer), "tool_content": tool_content_list}
    except Exception as e:
        logger.error(f"Error extracting response: {e}")
        return {"answer": "Error processing response", "tool_content": []}


# 初始化 Agent
agent_skills = create_skill_agent()


async def event_generator(req: QueryRequest, stream_args: dict) -> AsyncGenerator[str, None]:
    """统一的流式事件生成器"""
    logger.info(f"Request_Args: {req}")
    try:
        for stream_mode, data in agent_skills.stream(**stream_args):
            res = None

            if stream_mode == "custom":
                logger.debug(f"Custom stream data: {data}")
                res = StreamResponse(
                    type="tools_custom",
                    event=data.get("func_name", "unknown"),
                    data=data.get("data", {}),
                    agent="tools"
                )

            elif stream_mode == "messages":
                token, metadata = data
                node = metadata.get('langgraph_node', 'unknown')

                if node == "model":
                    content_blocks = getattr(token, 'content_blocks', [])
                    for block in content_blocks:
                        b_type = block.get("type", "text")
                        content_val = ""
                        if b_type == "text":
                            content_val = block.get('text', '')
                        elif b_type == "reasoning":
                            content_val = block.get('reasoning', '')

                        if content_val and req.stream_mode == "MESSAGES":
                            res = StreamResponse(type=str(b_type), event='token', content=content_val, agent=node)
                            res_json = res.model_dump_json()
                            yield f"data: {res_json}\n\n"
                    continue

                elif node == "tools":
                    _data = token.model_dump() if hasattr(token, 'model_dump') else dict(token)
                    content = _data.get("content", "")
                    func_name = _data.get("name", "") or "tool_call"

                    if func_name in FUNCS_WITH_JSON_OUTPUT:
                        try:
                            content = json.loads(content) if isinstance(content, str) else content
                        except json.JSONDecodeError:
                            pass
                        res = StreamResponse(type='tools', event=str(func_name), data=content, agent=node)
                    else:
                        res = StreamResponse(type='tools', event=str(func_name), content=str(content), agent=node)

                    if res and req.stream_mode == "MESSAGES" and "not found." not in str(res.content).lower():
                        res_json = res.model_dump_json()
                        logger.info(f"session_id: {req.session_id} >>> Update_Response: {res_json}")
                        yield f"data: {res_json}\n\n"
                    continue

            elif stream_mode == "updates":
                if isinstance(data, dict):
                    for source, update in data.items():
                        if source == "__interrupt__":
                            try:
                                val = update[-1].value if update else {}
                                action_reqs = val.get("action_requests", [])
                                review_cfgs = val.get("review_configs", [])
                                
                                if action_reqs and review_cfgs:
                                    review_cfgs_data = review_cfgs[-1]
                                    review_cfgs_data["args"] = action_reqs[-1].get("args", {})
                                    
                                    res = StreamResponse(
                                        type="interrupt",
                                        event=action_reqs[-1].get("name", "unknown"),
                                        data=review_cfgs_data,
                                        agent="tools"
                                    )
                                    res_json = res.model_dump_json()
                                    logger.info(f"session_id: {req.session_id} >>> Interrupt_Response: {res_json}")
                                    yield f"data: {res_json}\n\n"
                            except (IndexError, KeyError, TypeError) as e:
                                logger.warning(f"Interrupt parsing error: {e}")

                        elif source in ("model", "tools"):
                            try:
                                last_msg = update["messages"][-1]
                                event = getattr(last_msg, 'name', None) or last_msg.get('name', source) if isinstance(last_msg, dict) else source
                                msg_content = last_msg.content if hasattr(last_msg, 'content') else last_msg.get('content', '')
                                if not msg_content:
                                    continue
                                if isinstance(msg_content, str) and event in FUNCS_WITH_JSON_OUTPUT:
                                    try:
                                        msg_content = json.loads(msg_content)
                                    except json.JSONDecodeError:
                                        pass
                                else:
                                    msg_content = str(msg_content)
                                res = StreamResponse(
                                    type=source,
                                    event=str(event),
                                    data=(msg_content if source == "tools" else ""),
                                    content=(msg_content if source == "model" else ""),
                                    agent=source
                                )
                                res_json = res.model_dump_json()
                                logger.info(f"session_id: {req.session_id} >>> Update_Response: {res_json}")
                                if req.stream_mode == "UPDATES":
                                    yield f"data: {res_json}\n\n"
                            except (IndexError, KeyError):
                                pass

            if res and stream_mode != "messages":
                if req.stream_mode == "MESSAGES" and stream_mode == "custom":
                    res_json = res.model_dump_json()
                    logger.info(f"session_id: {req.session_id} >>> Custom_Response: {res_json}")
                    yield f"data: {res_json}\n\n"
                elif req.stream_mode == "UPDATES" and stream_mode == "updates":
                    pass

        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"Stream generation error: {e}", exc_info=True)
        error_res = StreamResponse(type="error", event="system", content=str(e), agent="system")
        res_json = error_res.model_dump_json()
        logger.error(f"Error response: {res_json}")
        yield f"data: {res_json}\n\n"
        yield "data: [DONE]\n\n"


# =================路由：核心业务=================
@app.post("/skills")
async def skills_endpoint(req: QueryRequest):
    """核心流式逻辑入口"""
    input_data = {"messages": [HumanMessage(content=req.message)]}
    uuid_v4 = req.session_id or str(uuid4())
    config = {"configurable": {"thread_id": uuid_v4}}

    stream_args = {
        "input": input_data,
        "config": config,
        "stream_mode": ["messages", "updates", "custom"]
    }

    logger.info(f"Processing request for session {req.session_id} with message: {req.message}")

    return StreamingResponse(
        event_generator(req, stream_args),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Type": "text/event-stream; charset=utf-8"
        }
    )


@app.post("/assis")
async def assis_endpoint(req: QueryRequest):
    """非流式/更新模式入口 (兼容旧接口)"""
    req.stream_mode = "UPDATES"
    return await skills_endpoint(req)


@app.post("/assis/stream")
async def assis_stream_endpoint(req: QueryRequest):
    """纯消息流式入口 (兼容旧接口)"""
    req.stream_mode = "MESSAGES"
    return await skills_endpoint(req)


# =================主入口=================
def is_debugging() -> bool:
    """检测当前是否在调试器环境下运行"""
    debuggers = {'pydevd', 'debugpy', 'pdb'}
    return any(mod in sys.modules for mod in debuggers)


def run_server():
    """启动 Uvicorn 服务器，自动处理调试模式下的事件循环冲突"""
    metrics_thread = threading.Thread(target=start_metrics_server, daemon=True)
    metrics_thread.start()

    if is_debugging():
        config = uvicorn.Config(app, host=settings.host, port=settings.port, log_level="info")
        server = uvicorn.Server(config)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        loop.run_until_complete(server.serve())
    else:
        uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    run_server()
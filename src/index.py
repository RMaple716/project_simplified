"""
旅游行程规划后端服务 - FastAPI 主入口

统一接口规范：
- 响应格式：{code: int, msg: str, data: any}
- 命名规范：英文小写下划线
- 时间格式：HH:mm
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from dotenv import load_dotenv

# 加载环境变量
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import src.routes

# 创建 FastAPI 应用
app = FastAPI(
    title="旅游行程规划后端服务",
    description="统一接口规范 | 响应格式: {code, msg, data}",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 数据库自动建表
from src.database import engine, Base
from src.models import db_models  # 导入所有模型


@app.on_event("startup")
async def startup():
    """应用启动时初始化"""
    # 1. 数据库建表
    print("\n" + "="*60)
    print("🚀 正在检查数据库表...")
    try:
        Base.metadata.create_all(bind=engine)
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        print(f"✅ 当前数据库共有 {len(tables)} 个表:")
        for table in sorted(tables):
            print(f"   - {table}")
    except Exception as e:
        print(f"❌ 数据库初始化失败: {e}")
    print("="*60 + "\n")

    # 2. 初始化事件总线（增强版）
    from src.services.negotiation_event_bus import event_bus
    # 启用持久化（如需）
    if os.getenv("ENABLE_EVENT_PERSISTENCE", "false").lower() == "true":
        event_bus.enable_persistence()
        print("✅ 协商事件持久化已启用")
    # 启动TTL清理（默认5分钟检查一次）
    event_bus.start_cleanup_task(interval_seconds=300)
    print("✅ 事件总线TTL清理任务已启动")
    print(f"✅ 事件总线版本: 增强版（WebSocket + 持久化 + Agent通信）")


@app.on_event("shutdown")
async def shutdown():
    """应用关闭时清理"""
    from src.services.negotiation_event_bus import event_bus
    event_bus.stop_cleanup_task()
    print("✅ 事件总线TTL清理任务已停止")


# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "msg": f"服务器内部错误: {str(exc)}",
            "data": None
        }
    )

# 注册路由
app.include_router(src.routes.health_router)
app.include_router(src.routes.requirement_router)
app.include_router(src.routes.task_router)
app.include_router(src.routes.agent_router)
app.include_router(src.routes.itinerary_router)
app.include_router(src.routes.validate_router)
app.include_router(src.routes.static_data_router)
app.include_router(src.routes.integration_router)
app.include_router(src.routes.nlp_router)
app.include_router(src.routes.weather_router)
app.include_router(src.routes.navigation_router)
app.include_router(src.routes.auth_router)
# 【新增】WebSocket 路由
app.include_router(src.routes.ws_router)

# 根路径
@app.get("/")
async def root():
    return {
        "service": "travel-planner-backend",
        "version": "1.0.0",
        "docs": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=9092)
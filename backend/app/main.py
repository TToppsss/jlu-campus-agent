import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agent, auth, conversations, edu, health
from app.config import settings
from app.edu.heartbeat import heartbeat_loop
from app.oa.crawler import refresh_oa_notices
from app.rag.ingest import ingest_notices_by_ids

app = FastAPI(title=settings.app_name)


async def oa_refresh_loop() -> None:
    while True:
        try:
            result = await refresh_oa_notices(max_pages=2)
            changed_ids = result.get("changed_ids", [])
            if changed_ids:
                ingest_result = await ingest_notices_by_ids(changed_ids)
                print(
                    f"OA 增量更新完成：扫描 {result['fetched']} 条，新增/更新 {len(changed_ids)} 条，向量化 {ingest_result['chunks']} 个 chunks"
                )
            else:
                print(f"OA 增量更新完成：扫描 {result['fetched']} 条，暂无新增或变更")
        except Exception as e:
            print(f"OA 刷新或向量化失败：{e}")
        await asyncio.sleep(15 * 60)


@app.on_event("startup")
async def start_oa_refresh_task() -> None:
    asyncio.create_task(oa_refresh_loop())
    asyncio.create_task(heartbeat_loop())

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api/auth")
app.include_router(conversations.router, prefix="/api/conversations")
app.include_router(edu.router, prefix="/api/edu")
app.include_router(agent.router, prefix="/api/agent")

import os
import asyncio
from uvicorn import run
from starlette.responses import HTMLResponse, FileResponse
from aioredis import create_redis_pool, Redis
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from tortoise.exceptions import OperationalError
from tortoise import Tortoise

from apps import create_app
from apps.configs import config
from apps.tools.scheduler_tools import *
from apps.tools.db_config import init_db as config_init_db

app = create_app()


async def get_redis_pool() -> Redis:
    redis = await create_redis_pool(
        f"redis://:{config.REDIS_PASSWORD}@{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB}?encoding=utf-8")
    return redis


async def heartbeat():
    while True:
        try:
            # 试图执行简单的查询，确保数据库连接正常
            await User.filter(pk=1).first()
            print(f"{datetime.datetime.now()}数据库连接正常")
        except OperationalError:
            print("数据库连接失败，正在尝试重新连接...")
            await config_init_db(app)  # 如果连接失败，重新初始化数据库连接
        await asyncio.sleep(30)  # 每10秒检查一次数据库连接


@app.on_event("startup")
async def startup_event():
    # redis
    app.state.redis = await get_redis_pool()
    asyncio.create_task(heartbeat())
    scheduler = AsyncIOScheduler()
    # 每 2分钟运行一次， 下载文件
    # scheduler.add_job(down_file_tasks, "interval", seconds=60 * 2, max_instances=5, misfire_grace_time=3600)
    scheduler.add_job(tortoise_orm_survival, "interval", seconds=60 * 60, max_instances=5, misfire_grace_time=3600)
    scheduler.add_job(update_interpret_databaase_data_scheduler, "interval", seconds=60 * 60, max_instances=5, misfire_grace_time=3600)
    scheduler.start()


@app.on_event("shutdown")
async def shutdown_event():
    app.state.redis.close()
    await app.state.redis.wait_closed()
    await Tortoise.close_connections()


@app.get("/", tags=['index'])
async def index():
    """首页 """
    data = open('static/index.html', 'r', encoding='utf8').read()
    return HTMLResponse(content=data)


@app.get("/robots.txt", tags=['robots'])
async def robots():
    """robots """
    return FileResponse(path="./robots.txt")


if __name__ == "__main__":
    print("启动")
    print("文档地址：http://127.0.0.1/docs")
    run("main:app", host="0.0.0.0", port=5026, debug=True, reload=True, lifespan="on", workers=4)

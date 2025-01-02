#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Time    : 2023/7/6 9:54
# @Author  : LJ
# @File    : __init__.py.py
from fastapi import APIRouter, Depends

from apps.apis import test_handler, apis_handler, base_handler, configuration_handler, inspect_handler, \
    down_file_handler
from apps.tools import check_token
from apps.configs import config

api_router = APIRouter()

dependencies = []
if not config.DEBUG:
    dependencies = [Depends(check_token)]
"""
注册路由
"""
api_router.include_router(test_handler.router, prefix='/test', tags=["测试"])
api_router.include_router(apis_handler.router, prefix='/apis', tags=["通用"])
api_router.include_router(base_handler.router, prefix='/base', tags=["基础模块"], dependencies=dependencies)
api_router.include_router(configuration_handler.router, prefix='/config', tags=["数据配置"], dependencies=dependencies)
api_router.include_router(inspect_handler.router, prefix='/inspect', tags=["实验"], dependencies=dependencies)
api_router.include_router(down_file_handler.router, prefix='/down_file', tags=["下载数据"], dependencies=dependencies)

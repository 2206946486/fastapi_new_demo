#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Time    : 2023/7/6 14:21
# @Author  : LJ
# @File    : test_handler.py
import random
import os

from fastapi import APIRouter, Body, Request
from fastapi.responses import FileResponse
from typing import List
from tortoise.query_utils import Prefetch
from apps.tools.my_celery.celery_tasks import get_user_task, update_interpret_databaase_data


from apps.tools import res, State

router = APIRouter()


@router.get("/test", summary="测试数据显示")
async def test():
    return res(data="这是一条测试数据")


@router.get("/get_user_task_info", summary="测试异步任务")
async def get_user_task_info():
    get_user_task.delay()
    return res()


@router.get("/get_user_task_info1", summary="测试异步任务1")
async def get_update_interpret_databaase_data():
    update_interpret_databaase_data.delay()
    return res()
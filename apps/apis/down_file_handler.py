#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Time    : 2024/5/14 16:05
# @Author  : LJ
# @File    : down_file_handler.py
import os
import io
import re
import datetime
import copy
import json
import pandas as pd


from fastapi import APIRouter, Body, Form, UploadFile, File, Request, HTTPException
from typing import List
from datetime import timedelta
from tortoise.queryset import Q
from fastapi.responses import StreamingResponse, FileResponse

from apps.models import DownloadFilsTask
from apps.tools.my_celery.celery_tasks import *
from apps.tools import State, res, get_user_by_request, get_request_info_by_down_file


router = APIRouter()


@router.post("/down_project_sample_func", summary="项目分配数据导出")
async def down_project_sample_func(request: Request, start_time: str = Body(""), end_time: str = Body(""),
                                   data_ids: List[int] = Body([])):
    name, homepage_name, homepage, uid = await get_request_info_by_down_file(request)
    print(f"{start_time=}, {end_time=}, {data_ids=}")
    assert any([all([start_time, end_time]), data_ids]), State.PARAMS_ERROR
    obj = await DownloadFilsTask.create(name=name, module_name=homepage_name, module_path=homepage, user_id=uid,
                                        start_time=start_time, end_time=end_time, parameter=str(data_ids),
                                        created_at=datetime.datetime.now())
    down_project_sample.delay(obj.id, start_time=start_time, end_time=end_time, parameter=data_ids)
    return res()


@router.post("/shengxin_management_data_func", summary="生信数据导出")
async def shengxin_management_data_func(request: Request, start_time: str = Body(""), end_time: str = Body(""),
                                        data_ids: List[int] = Body([])):
    name, homepage_name, homepage, uid = await get_request_info_by_down_file(request)
    assert any([all([start_time, end_time]), data_ids]), State.PARAMS_ERROR
    obj = await DownloadFilsTask.create(name=name, module_name=homepage_name, module_path=homepage, user_id=uid,
                                        start_time=start_time, end_time=end_time, parameter=str(data_ids),
                                        created_at=datetime.datetime.now())
    shengxin_management_data.delay(obj.id, start_time=start_time, end_time=end_time, parameter=data_ids)
    return res()


@router.post("/interpreting_management_data_func", summary="解读数据导出")
async def interpreting_management_data_func(request: Request, start_time: str = Body(""), end_time: str = Body(""),
                                            data_ids: List[int] = Body([])):
    name, homepage_name, homepage, uid = await get_request_info_by_down_file(request)
    print(f"{start_time=}, {end_time=}, {data_ids=}")
    assert any([all([start_time, end_time]), data_ids]), State.PARAMS_ERROR
    obj = await DownloadFilsTask.create(name=name, module_name=homepage_name, module_path=homepage, user_id=uid,
                                        start_time=start_time, end_time=end_time, parameter=str(data_ids),
                                        created_at=datetime.datetime.now())
    interpreting_management_data.delay(obj.id, start_time=start_time, end_time=end_time, parameter=data_ids)
    return res()


@router.post("/interpreting_database_func", summary="解读数据库-数据导出")
async def interpreting_database_func(request: Request, start_time: str = Body(""), end_time: str = Body(""),
                                     data_ids: List[int] = Body([])):
    name, homepage_name, homepage, uid = await get_request_info_by_down_file(request)
    print(f"{start_time=}, {end_time=}, {data_ids=}")
    assert any([all([start_time, end_time]), data_ids]), State.PARAMS_ERROR
    obj = await DownloadFilsTask.create(name=name, module_name=homepage_name, module_path=homepage, user_id=uid,
                                        start_time=start_time, end_time=end_time, parameter=str(data_ids),
                                        created_at=datetime.datetime.now())
    interpreting_database.delay(obj.id, start_time=start_time, end_time=end_time, parameter=data_ids)
    return res()
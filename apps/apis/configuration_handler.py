#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Time    : 2023/7/12 16:27
# @Author  : LJ
# @File    : configuration_handler.py
import os
import io
import re
import datetime
import copy

from fastapi import APIRouter, Body, Form, UploadFile, File, Request
from typing import List
from tortoise.queryset import Q
from fastapi.responses import StreamingResponse, FileResponse

from apps.tools import res, State, formatting_time, get_user_by_request, get_user_name, get_dataoption_info
from apps.models import User, ProjectInfo, OutsourcerInfo, OutsourcerProductInfo

router = APIRouter()


#  产品
# @router.get("/get_all_projects", summary="获取所有产品")
# async def get_all_projects(search: str = "", page: int = 1, limit: int = 10):
#     first_data = await ProjectInfo.filter(is_delete=0, pid=0).values()
#     for second in first_data:
#         second_data = await ProjectInfo.filter(is_delete=0, pid=second.get("id")).values()
#         second_data = formatting_time(second_data)
#         second["second_data"] = second_data
#         for third in second_data:
#             third_query = ProjectInfo.filter(is_delete=0, pid=third.get("id")).filter(Q(name__icontains=search) |
#                                                                                       Q(illustrate__icontains=search))
#             third_data = await third_query.offset((page - 1) * limit).limit(limit).values()
#             third_data = formatting_time(third_data)
#             total = await third_query.count()
#             for third in third_data:
#                 third["user"] = await get_user_name(third["user_id"])
#             third["second_data"] = third_data
#             third["total"] = total
#     return res(data=first_data)

@router.get("/get_all_projects", summary="获取所有产品")
async def get_all_projects(search: str = ""):
    data = await ProjectInfo.filter(is_delete=0, name__icontains=search.strip()).values()
    for item in data:
        item["user"] = await get_user_name(item["user_id"])
    return res(data=data)


@router.get("/get_all_projects_list", summary="获取所有产品的下拉框数据")
async def get_all_projects_list():
    data = await ProjectInfo.filter(is_delete=0, pid=0).values()
    r_data = []
    for item in data:
        item_data = dict(value=item["id"],  label=item["name"], children=[], cycle=item["cycle"])
        pid_data = await ProjectInfo.filter(is_delete=0, pid=item["id"]).values()
        t_data = []
        for t_item in pid_data:
            t_item_data = dict(value=t_item["id"],  label=t_item["name"], children=[], cycle=t_item["cycle"])
            three_data = await ProjectInfo.filter(is_delete=0, pid=t_item["id"]).values()
            th_data = []
            for th_item in three_data:
                th_item_data = dict(value=th_item["id"],  label=th_item["name"] + " " + th_item["illustrate"], cycle=th_item["cycle"])
                th_data.append(th_item_data)
            t_item_data["children"] = th_data
            t_data.append(t_item_data)
        item_data["children"] = t_data
        r_data.append(item_data)

    return res(data=r_data)


@router.post("/add_projects", summary="增加产品")
async def add_projects(request: Request,
                       pid: int = Body(0),
                       name: str = Body(...),
                       illustrate: str = Body(""),
                       cycle: int = Body(7)):
    if pid:
        assert await ProjectInfo.filter(pk=pid).exists(), State.DATA_NOT_EXISTENCE
    uid, _ = await get_user_by_request(request)
    await ProjectInfo.create(pid=pid, name=name, illustrate=illustrate, cycle=cycle, user_id=uid)
    return res()


@router.post("/update_projects", summary="修改产品")
async def update_projects(request: Request, pid: int = Body(0), name: str = Body(...), illustrate: str = Body(""),
                          cycle: int = Body(7), id: int = Body(...)):
    assert await ProjectInfo.filter(pk=id).exists(), State.DATA_NOT_EXISTENCE
    if pid:
        assert await ProjectInfo.filter(pk=pid).exists(), State.DATA_NOT_EXISTENCE
    uid, _ = await get_user_by_request(request)
    await ProjectInfo.filter(id=id).update(pid=pid, name=name, illustrate=illustrate, cycle=cycle, user_id=uid)
    return res()


@router.delete("/delete_projects", summary="禁用/启用产品")
async def delete_projects(id: int = Body(...), is_delete: bool = Body(True)):
    await ProjectInfo.filter(Q(pk=id) | Q(pid=id)).update(is_delete=is_delete)
    return res()


#  外包商
@router.get("/get_all_outsourcer", summary="获取所有外包商")
async def get_all_outsourcer(search: str = "", page: int = 1, limit: int = 10):
    query = OutsourcerInfo.filter(is_delete=0).filter(Q(name__icontains=search) | Q(address__icontains=search) |
                                                      Q(phone__icontains=search))
    total = await query.count()
    data = await query.order_by("-id").offset((page - 1) * limit).limit(limit).values()
    data = formatting_time(data)
    for item in data:
        item["user"] = await get_user_name(item["user_id"])
    return res(data=dict(data=data, total=total))


@router.post("/add_outsourcer", summary="增加外包商")
async def add_outsourcer(reuqest: Request, name: str = Body(...), address: str = Body(""), contacts: str = Body(""),
                         phone: str = Body("")):
    uid, _ = await get_user_by_request(reuqest)
    assert not await OutsourcerInfo.filter(name=name).exists(), State.DATA_EXISTENCE
    await OutsourcerInfo.create(name=name, address=address, contacts=contacts, phone=phone, user_id=uid)
    return res()


@router.post("/update_outsourcer", summary="修改外包商")
async def update_outsourcer(reuqest: Request, name: str = Body(...), address: str = Body(""), contacts: str = Body(""),
                            phone: str = Body(""), id: int = Body(...)):
    uid, _ = await get_user_by_request(reuqest)
    assert not await OutsourcerInfo.filter(name=name).filter(~Q(id=id)).exists(), \
        State.DATA_EXISTENCE
    await OutsourcerInfo.filter(id=id).update(name=name, address=address, contacts=contacts, phone=phone, user_id=uid)
    return res()


@router.delete("/delete_outsourcer", summary="禁用/启用外包商")
async def delete_outsourcer(ids: List[int] = Body(...), is_delete: bool = Body(True)):
    await OutsourcerInfo.filter(pk__in=ids).update(is_delete=is_delete)
    return res()


#  外包商产品
@router.get("/get_all_outsourcer_prodcut", summary="获取所有外包商-外包产品")
async def get_all_outsourcer_prodcut(search: str = "", page: int = 1, limit: int = 10):
    query = OutsourcerProductInfo.filter(is_delete=0).filter(Q(name__icontains=search) | Q(address__icontains=search) |
                                                             Q(phone__icontains=search) | Q(contacts__icontains=search))
    total = await query.count()
    data = await query.order_by("-id").offset((page - 1) * limit).limit(limit).values()
    data = formatting_time(data)
    for item in data:
        item["user"] = await get_user_name(item["user_id"])
        outsourcer = await OutsourcerInfo.filter(pk=item["outsourcer_id"]).first()
        item["outsourcer"] = outsourcer.name
    return res(data=dict(data=data, total=total))


@router.post("/add_outsourcer_product", summary="增加外包商-外包产品")
async def add_outsourcer_product(reuqest: Request, name: str = Body(...), outsourcer_id: int = Body(...),
                                 address: str = Body(""), contacts: str = Body(""), phone: str = Body(""),
                                 cycle: int = Body(...)):
    uid, _ = await get_user_by_request(reuqest)
    assert not await OutsourcerProductInfo.filter(name=name, outsourcer_id=outsourcer_id).exists(), State.DATA_EXISTENCE
    await OutsourcerProductInfo.create(name=name, outsourcer_id=outsourcer_id, address=address, contacts=contacts,
                                       phone=phone, user_id=uid, cycle=cycle)
    return res()


@router.post("/update_outsourcer_product", summary="修改外包商-外包产品")
async def update_outsourcer_product(reuqest: Request, name: str = Body(...), outsourcer_id: int = Body(...),
                                    address: str = Body(""), contacts: str = Body(""), phone: str = Body(""),
                                    id: int = Body(...), cycle: int = Body(...)):
    uid, _ = await get_user_by_request(reuqest)
    assert not await OutsourcerProductInfo.filter(name=name, outsourcer_id=outsourcer_id).filter(~Q(id=id)).exists(), \
        State.DATA_EXISTENCE
    await OutsourcerProductInfo.filter(id=id).update(name=name, outsourcer_id=outsourcer_id, address=address,
                                                     contacts=contacts, phone=phone, user_id=uid, cycle=cycle)
    return res()


@router.delete("/delete_outsourcer_product", summary="禁用/启用外包商-外包产品")
async def delete_outsourcer_product(ids: List[int] = Body(...), is_delete: bool = Body(True)):
    await OutsourcerProductInfo.filter(pk__in=ids).update(is_delete=is_delete)
    return res()


@router.get("/get_all_outsourcer_prodcut_list", summary="获取所有外包商-外包产品列表")
async def get_all_outsourcer_prodcut_list(outsourcer_id: int):
    data = await OutsourcerProductInfo.filter(is_delete=0).filter(outsourcer_id=outsourcer_id).values("id", "name")
    return res(data=data)
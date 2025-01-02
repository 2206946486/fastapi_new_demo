#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Time    : 2023/7/6 16:11
# @Author  : LJ
# @File    : apis_handler.py
import hashlib
import random

from fastapi import APIRouter, Body, Form, Request, HTTPException, File, UploadFile, Depends
from tortoise.queryset import Q

from apps.tools import res, State, authenticate_user, create_token, get_user_by_request, pwd_context, Sample, \
    get_dataoption_info, get_completion_status_info_tool, get_prodcut_level, get_user_name, get_sample_outsource_data
from apps.models import User, InspectOrderSample, InspectOrder, SampleBioInformatics, ProjectInfo, CompletionStatus
from apps.configs import config

router = APIRouter()


@router.post("/token", summary="获取token, 接口文档模拟登录")
async def token(request: Request, username: str = Form(...), password: str = Form(...)):
    password = password if len(password) == 32 else hashlib.md5(password.encode()).hexdigest()
    # print(f"{password=}")
    user = await authenticate_user(username, password)
    assert user, State.USER_PASSWORD_ERR
    encoded_jwt = await create_token(request, user)
    return {"access_token": encoded_jwt, "token_type": "bearer"}


@router.post("/login", summary="登录")
async def login(request: Request, username: str = Body(...), password: str = Body(...)):
    user = await authenticate_user(username, password)
    assert user, State.USER_PASSWORD_ERR
    encoded_jwt = await create_token(request, user)
    assert encoded_jwt, State.FAILURE
    return res(data=dict(access_token=encoded_jwt, token_type="bearer"))


@router.put("/update_user_password", summary="修改用户密码")
async def update_user_password(request: Request, new_password: str = Body(...), r_new_password: str = Body(...)):
    """
        暂缓，等登录验证完成后根据登录用户获取用户信息，修改密码
    :param old_password:
    :param new_password:
    :param r_new_password:
    :return:
    """
    uid, _ = await get_user_by_request(request)
    user = await User.filter(pk=uid).first()
    assert user, State.NO_USER
    # if old_password == new_password:
    #     return res(State.SAME_PASSWORD)
    if new_password != r_new_password:
        return res(State.DIFFERENT_PASSWORD)
    password = pwd_context.hash(new_password)
    user.password = password
    user.is_initialize = 1
    await user.save()
    return res()


@router.post("/send_code", summary="发送验证码")
async def send_code(request: Request, phone: str = Body(...), type: int = Body(1)):
    """
    :param request:
    :param phone: 手机号
    :param type: 1：身份认证验证码， 2：修改密码认证码
    :return:
    """
    assert await User.filter(phone=phone).exists(), State.INVALID_PHONE
    code = str(random.randint(000000, 999999))
    tmp_code = config.SMS_213885074 if type == 1 else config.SMS_213885070
    await Sample.main_async(phone, code, tmp_code)
    phone = phone if type == 1 else f"reset_{phone}"
    await request.app.state.redis.set(phone, code)
    await request.app.state.redis.expire(phone, 60 * 30)
    # print(f"{phone=}:{code}")
    return res()


@router.post("/phone_login", summary="手机号登录")
async def phone_login(request: Request, phone: str = Body(...), code: str = Body(...)):
    redis_code = await request.app.state.redis.get(phone)
    assert redis_code == code, State.INVALID_CODE
    user = await User.filter(phone=phone).first()
    assert user, State.INVALID_CODE
    encoded_jwt = await create_token(request, user)
    assert encoded_jwt, State.FAILURE
    return res(data=dict(access_token=encoded_jwt, token_type="bearer"))


@router.post('/reset_password', summary="重置密码")
async def reset_password(request: Request, phone: str = Body(...), code: str = Body(...)):
    redis_code = await request.app.state.redis.get(f"reset_{phone}")
    assert redis_code == code, State.INVALID_CODE
    user = await User.filter(phone=phone).first()
    assert user, State.INVALID_CODE
    password = pwd_context.hash("e10adc3949ba59abbe56e057f20f883e")
    user.password = password
    user.is_initialize = 0
    await user.save()
    return res()


@router.post("/get_all_sample_bioinformatics", summary="获取所有的生信数据")
async def get_all_sample_bioinformatics(request: Request):
    """
    """
    # uid, _ = await get_user_by_request(request)
    body = await request.json()
    # print(f"{body=}")
    page = body.pop("page")
    limit = body.pop("limit")
    query = InspectOrderSample.filter(is_delete=0, is_allocation=1)
    # query = query.filter(**body)
    total = await query.count()
    data = await query.order_by("-id").offset((page - 1) * limit).limit(limit).values()
    # data = await query.order_by("-id").values()
    for item in data:
        item["sample_type_info"] = await get_dataoption_info(item["sample_type"])
        item["unit_info"] = await get_dataoption_info(item["unit"])
        item["sample_attribute_info"] = await get_dataoption_info(item["sample_attribute"])
        item["is_compare_info"] = await get_dataoption_info(item["is_compare"])
        item["gather_dt"] = str(item["gather_dt"])[:10]
        item["deadline_dt"] = str(item["deadline_dt"])[:10]
        item["charge_status_info"] = await get_dataoption_info(item["charge_status"])
        item["charge_dt"] = str(item["charge_dt"])[:10] if item["charge_dt"] else ""
        # 当前实验流程
        item["completion_data"] = await get_completion_status_info_tool(item["completion_id"])
        item["is_complete_info"] = await get_dataoption_info(item["is_complete"])
        project = await ProjectInfo.filter(pk=item["project_id"]).first()
        item["project"] = project.name
        item["capture_probe"] = project.illustrate
        item["project_info"] = await get_prodcut_level(item["project_id"], product_info=[])
        order = await InspectOrder.filter(pk=item["order_id"]).first()
        item["nickname"] = order.nickname
        item["sex"] = order.sex
        item["age"] = order.age
        item["report_phone"] = order.report_phone
        item["user"] = await get_user_name(item["user_id"])
        # # 捕获探针
        # last_probe = await CompletionStatus.filter(sample_id=item["id"], completion_status=8).order_by("-id").first()
        # item["capture_probe"] = ""
        # if last_probe:
        #     if last_probe.txt_content:
        #         item["capture_probe"] = eval(last_probe.txt_content).get("capture_probe")
        last_data = await CompletionStatus.filter(sample_id=item["id"], completion_status=6).order_by("-id").first()
        item["nucleic_type"] = ""
        if last_data:
            if last_data.txt_content:
                item["nucleic_type"] = eval(last_data.txt_content).get("nucleic_type")
        bioinformatic = await SampleBioInformatics.filter(sample_id=item["id"]).first()
        if bioinformatic:
            item["execute_id"] = bioinformatic.id
            item["execute"] = await get_user_name(bioinformatic.execute_id) if bioinformatic.execute_id else ""
            item["execute_at"] = str(bioinformatic.execute_at)[:19] if bioinformatic.execute_at else ""
            item["approve"] = await get_user_name(bioinformatic.approve_id) if bioinformatic.approve_id else ""
            item["approve_at"] = str(bioinformatic.approve_at)[:19] if bioinformatic.approve_at else ""
            item["approve_desc"] = bioinformatic.approve_desc
            item["result"] = bioinformatic.result
            if bioinformatic.approve_status == 0:
                item["approve_status_info"] = "待提交"
            elif bioinformatic.approve_status == 1:
                item["approve_status_info"] = "已审核"
            elif bioinformatic.approve_status == 2:
                item["approve_status_info"] = "已拒绝"
            elif bioinformatic.approve_status == 3:
                item["approve_status_info"] = "待审核"
            else:
                item["approve_status_info"] = "未知"
        else:
            item["execute_id"] = None
            item["execute"] = ""
            item["execute_at"] = ""
            item["approve"] = ""
            item["approve_at"] = ""
            item["approve_desc"] = ""
            item["approve_status_info"] = "待领取"
            item["result"] = ""
    return res(data=dict(data=data, total=total))
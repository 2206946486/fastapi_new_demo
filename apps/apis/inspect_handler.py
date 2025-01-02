#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Time    : 2023/7/18 8:35
# @Author  : LJ
# @File    : inspect_handler.py
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

from apps.tools import res, State, formatting_time, get_user_by_request, get_user_name, get_dataoption_info, \
    get_sample_order_no, save_file, calculation_size, get_file_model, get_completion_status_info_tool, get_salple_info, \
    get_sample_no, get_order_user, get_prodcut_level, send_email, get_bioinformatics_data, is_number, \
    get_dataoption_data, get_department_data, convert_percentage, get_sample_info, get_bio_info
from apps.models import InspectOrder, InspectOrderSample, InspectOrderFile, FileData, ProjectInfo, CompletionStatus, \
    InspectOrderSampleFile, OutsourcerInfo, Department, CompletionStatusFile, SampleInterpreting, SampleInterpretingFile,\
    SampleNo, SamplePlaceOrder, SampleBioInformatics, SampleBioInformaticsFile, OutsourcerProductInfo, \
    SampleReportSendLog, InterpretingDataBase, InterpretBind
from apps.configs import config

router = APIRouter()


# 样本下单
@router.post("/get_all_sample_orders", summary="获取所有的样本订单")
async def get_all_sample_orders(request: Request):
    """获取样本下单数据
        data_type: 1：所有数据, 2：我的数据
    """
    uid, _ = await get_user_by_request(request)
    body = await request.json()
    page = body.pop("page")
    limit = body.pop("limit")
    data_type = body.pop("data_type")
    search = body.pop("search")
    query = InspectOrder.filter(is_delete=0).filter(Q(nickname__icontains=search) | Q(no__icontains=search))
    if data_type == 2:
        query = InspectOrder.filter(user_id=uid)
    for key in list(body.keys()):
        if key == "totalResult":
            body.pop("totalResult")
            continue
        if key == "receive_dt":
            receive_dt = body.pop("receive_dt")
            body["receive_dt__icontains"] = receive_dt
            continue
        if body[key] in [0, "", "-1", 1]:
            if key == "approve_status":
                if str(body[key]) == "-1":
                    body.pop(key)
            else:
                body.pop(key)
    query = query.filter(**body)
    data = await query.order_by("-id").offset((page - 1) * limit).limit(limit).values()
    total = await query.count()
    for item in data:
        item["cancer_species_info"] = await get_dataoption_info(item["cancer_species"])
        item["is_urgent_info"] = await get_dataoption_info(item["is_urgent"])
        item["send_user"] = await get_user_name(item["send_user_id"])
        item["user"] = await get_user_name(item["user_id"])
        if item["sex"] == 1:
            item["sex_info"] = "男"
        elif item["sex"] == 2:
            item["sex_info"] = "女"
        else:
            item["sex_info"] = "未知"
    data = formatting_time(
        data,
        args=[
            "created_at",
            "updated_at",
            "receive_dt"
        ])
    return res(data=dict(data=data, total=total))


@router.post("/get_sample_order_all_samples", summary="获取样本订单的所有样本数据")
async def get_sample_order_all_samples(request: Request):
    body = await request.json()
    page = body.pop("page")
    limit = body.pop("limit")
    order_id = body.pop("order_id")
    query = InspectOrderSample.filter(is_delete=0, order_id=order_id)
    query = query.filter(**body)
    data = await query.order_by("id").offset((page - 1) * limit).limit(limit).values()
    total = await query.count()
    for item in data:
        item["sample_type_info"] = await get_dataoption_info(item["sample_type"])
        item["unit_info"] = await get_dataoption_info(item["unit"])
        item["sample_attribute_info"] = await get_dataoption_info(item["sample_attribute"])
        item["user"] = await get_user_name(item["user_id"])
        # item["send_user"] = await get_user_name(item["send_user_id"])
        project = await ProjectInfo.filter(pk=item["project_id"]).first()
        item["project"] = project.name
        item["gather_dt"] = str(item["gather_dt"])[:10] if item["gather_dt"] else ""
        item["charge_dt"] = str(item["charge_dt"])[:10] if item["charge_dt"] else ""
        item["charge_status_info"] = await get_dataoption_info(item["charge_status"])
        item["project_info"] = await get_prodcut_level(item["project_id"], product_info=[])
    data = formatting_time(
        data,
        args=[
            "created_at",
            "updated_at"
        ])
    return res(data=dict(data=data, total=total))


@router.post("/add_sample_order", summary="增加样本订单数据")
async def add_sample_order(request: Request, nickname: str = Form(...), sex: int = Form(...), age: str = Form(...),
                           report_receive: str = Form(...), report_phone: str = Form(""), report_email: str = Form(""),
                           report_addr: str = Form(""), is_patient: int = Form(0), cancer_species: int = Form(...),
                           specific: str = Form(""), receive_dt: str = Form(...), hospital_num: str = Form(""),
                           hospital: str = Form(""), visiting_department: str = Form(""), doctor: str = Form(""),
                           send_user: int = Form(...), files: List[UploadFile] = File(None), samples: str = Form("[]"),
                           is_urgent: int = Form(...), sample_desc: str = Form("")):
    """
    因为涉及到文件上传，需要将样本数据序列化
    :param files:
    :param samples: [{"sample_type": value >> int, "sample_attribute": value >> int, "number": value >> float,
                      "sample_desc": value >> str, "receive_dt": value >> str, "cycle": value >> int,
                       "project_id": value >> int}]
    :return:
    """
    uid, _ = await get_user_by_request(request)
    no = await get_sample_no(uid)
    order = await InspectOrder.create(no=no, nickname=nickname, sex=sex, age=age, report_receive=report_receive,
                                      report_phone=report_phone, report_email=report_email, report_addr=report_addr,
                                      is_patient=is_patient, cancer_species=cancer_species, specific=specific,
                                      receive_dt=receive_dt, hospital_num=hospital_num, hospital=hospital,
                                      visiting_department=visiting_department, doctor=doctor, user_id=uid,
                                      send_user_id=send_user, is_urgent=is_urgent, sample_desc=sample_desc)
    if files:
        for file in files:
            file_id = await save_file(file, uid)
            await InspectOrderFile.create(data_id=order.id, file_id=file_id, file_type=0)
    samples_data = eval(samples)
    for index, item in enumerate(samples_data):
        sample_no = f"{no}-{str(index + 1)}"
        cycle = item["cycle"]
        deadline_dt = datetime.datetime.strptime(
            item["gather_dt"], "%Y-%m-%d") + datetime.timedelta(days=int(cycle))
        remind_dt = datetime.datetime.strptime(
            item["gather_dt"], "%Y-%m-%d") + datetime.timedelta(days=int(cycle) - 2)
        await InspectOrderSample.create(sample_no=sample_no, sample_type=item["sample_type"], number=item["number"],
                                        unit=item["unit"], sample_attribute=item["sample_attribute"],
                                        gather_dt=item["gather_dt"], sample_desc=item["sample_desc"],
                                        abnormal_desc=item["abnormal_desc"], cycle=item["cycle"],
                                        project_id=item["project_id"], order_id=order.id, deadline_dt=deadline_dt,
                                        remind_dt=remind_dt, user_id=uid, amount=item["amount"],
                                        charge_status=item["charge_status"],
                                        charge_dt=item["charge_dt"] if item["charge_dt"] != "" else None,
                                        is_complete=43, is_compare=item["is_compare"])
        await SampleNo.filter(no=no).update(status=1, use_dt=datetime.datetime.now(), use_user_id=uid)
    return res()


# @router.get("/get_sample_no", summary="获取样本编号")
# async def get_sample_no(request: Request):
#     print(f"{request=}")
#     uid, _ = await get_user_by_request(request)
#     no = await get_sample_no(uid)
#     return res(data=no)


@router.delete("/delete_sample_order", summary="删除样本下单")
async def delete_sample_order(ids: List[int] = Body(..., embed=True)):
    await InspectOrder.filter(pk__in=ids).update(is_delete=1)
    await InspectOrderSample.filter(order_id__in=ids).update(is_delete=1)
    return res()


@router.delete("/delete_sample_order_sample", summary="删除样本下单的样本")
async def delete_sample_order_sample(ids: List[int] = Body(..., embed=True)):
    await InspectOrderSample.filter(id__in=ids).update(is_delete=1)
    return res()


@router.post("/add_sample_order_sample", summary="新增样本下单的样本数据")
async def add_sample_order_sample(request: Request, order_id: int = Body(...),
                                  sample_type: int = Body(...), number: int = Body(0), unit: str = Body(...),
                                  sample_attribute: int = Body(...), gather_dt: str = Body(...),
                                  sample_desc: str = Body(""), abnormal_desc: str = Body(""), cycle: str = Body(7),
                                  project_id: int = Body(...), amount: float = Body(0.00),
                                  charge_status: int = Body(...), charge_dt: str = Body(None),
                                  is_compare: int = Body(...)):
    uid, _ = await get_user_by_request(request)
    deadline_dt = datetime.datetime.strptime(
        gather_dt, "%Y-%m-%d") + datetime.timedelta(days=int(cycle))
    remind_dt = datetime.datetime.strptime(
        gather_dt, "%Y-%m-%d") + datetime.timedelta(days=int(cycle) - 2)
    charge_dt = charge_dt or None
    order = await InspectOrder.filter(pk=order_id).first()
    sample_count = await InspectOrderSample.filter(order_id=order_id).count()
    no = f"{order.no}-{str(sample_count + 1)}"
    await InspectOrderSample.create(order_id=order_id, sample_type=sample_type, number=number,
                                    unit=unit, sample_attribute=sample_attribute, gather_dt=gather_dt,
                                    sample_desc=sample_desc, abnormal_desc=abnormal_desc, cycle=cycle,
                                    project_id=project_id, deadline_dt=deadline_dt, remind_dt=remind_dt, user_id=uid,
                                    sample_no=no, amount=amount, charge_status=charge_status, charge_dt=charge_dt,
                                    is_compare=is_compare)
    await SampleNo.filter(no=no).update(status=1, use_dt=datetime.datetime.now(), use_user_id=uid)
    return res()


@router.post("/update_sample_order_sample", summary="修改样本下单的样本数据")
async def update_sample_order_sample(request: Request, sample_type: int = Body(...), number: int = Body(0),
                                     unit: str = Body(...), sample_attribute: int = Body(...), gather_dt: str = Body(...),
                                     sample_desc: str = Body(""), abnormal_desc: str = Body(""), cycle: str = Body(7),
                                     project_id: int = Body(...), id: int = Body(...), amount: float = Body(0.00),
                                     charge_status: int = Body(...), charge_dt: str = Body(None),
                                     is_compare: int = Body(...)):
    uid, _ = await get_user_by_request(request)
    gather_dt = str(gather_dt)[:10]
    deadline_dt = datetime.datetime.strptime(
        gather_dt, "%Y-%m-%d") + datetime.timedelta(days=int(cycle))
    remind_dt = datetime.datetime.strptime(
        gather_dt, "%Y-%m-%d") + datetime.timedelta(days=int(cycle) - 2)
    charge_dt = charge_dt or None
    await InspectOrderSample.filter(id=id).update(sample_type=sample_type, number=number, unit=unit,
                                                  sample_attribute=sample_attribute, gather_dt=gather_dt,
                                                  sample_desc=sample_desc, abnormal_desc=abnormal_desc, cycle=cycle,
                                                  project_id=project_id, deadline_dt=deadline_dt, remind_dt=remind_dt,
                                                  user_id=uid, amount=amount, charge_status=charge_status,
                                                  charge_dt=charge_dt, is_compare=is_compare)
    return res()


@router.post("/update_sample_order", summary="修改样本订单数据")
async def update_sample_order(request: Request, nickname: str = Body(...), sex: int = Body(...), age: str = Body(...),
                              report_receive: str = Body(...), report_phone: str = Body(""),
                              report_email: str = Body(""), report_addr: str = Body(""), is_patient: int = Body(0),
                              cancer_species: int = Body(...), specific: str = Body(""), receive_dt: str = Body(...),
                              hospital_num: str = Body(""), hospital: str = Body(""),
                              visiting_department: str = Body(""), doctor: str = Body(""), sample_desc: str = Body(""),
                              send_user: int = Body(...), id: int = Body(...), is_urgent: int = Body(...)):
    uid, _ = await get_user_by_request(request)
    await InspectOrder.filter(id=id).update(nickname=nickname, sex=sex, age=age, report_receive=report_receive,
                                            report_phone=report_phone, report_email=report_email,
                                            report_addr=report_addr, is_patient=is_patient,
                                            cancer_species=cancer_species, specific=specific, receive_dt=receive_dt,
                                            hospital_num=hospital_num, hospital=hospital,
                                            visiting_department=visiting_department, doctor=doctor, user_id=uid,
                                            send_user_id=send_user, is_urgent=is_urgent, sample_desc=sample_desc)
    return res()


@router.get("/get_order_file", summary="获取样本下单附件")
async def get_order_file(order_id: int, search: str = "", page: int = 1, limit: int = 10):
    file_ids = await InspectOrderFile.filter(data_id=order_id).all()
    query = FileData.filter(
        pk__in=[
            item.file_id for item in file_ids],
        name__icontains=search)
    total = await query.count()
    files = await query.offset((page - 1) * limit).limit(limit).values()
    for item in files:
        item["submit"] = await get_user_name(item["submit_id"])
        item["size"] = calculation_size(int(item["size"]))
        item["created_at"] = str(item["created_at"])[:19]
    return res(data=dict(data=files, total=total))


@router.post("/add_file", summary="增加附件")
async def add_file(request: Request, data_id: int = Form(...), files: List[UploadFile] = File(...),
                   file_type: int = Form(...), model_type: str = Form(...)):
    model = get_file_model(model_type)
    uid, _ = await get_user_by_request(request)
    for file in files:
        file_id = await save_file(file, uid)
        await model.create(data_id=data_id, file_id=file_id, file_type=file_type)
    return res()


@router.delete("/delete_file", summary="删除附件")
async def delete_file(file_ids: List[int] = Body(...), model_type: str = Body(...)):
    model = get_file_model(model_type)
    await model.filter(file_id__in=file_ids).delete()
    files = await FileData.filter(pk__in=file_ids).all()
    for file in files:
        os.remove(file.file_path)
        await file.delete()
    return res()


@router.get("/download_file", summary="下载文件")
async def download_file(file_id: int):
    file = await FileData.filter(pk=file_id).first()
    if not file or not os.path.exists(file.file_path):
        return res(State.DATA_NOT_EXISTENCE)
    return FileResponse(path=file.file_path, filename=file.name)


@router.post("/assign_orders_sample", summary="人员分派样本实验单")
async def assign_orders_sample(request: Request, sample_ids: List[int] = Body(...), completion_status: int = Body(...),
                               express_company: str = Body(None), express_size: str = Body(""),
                               outsource_id: int = Body(None), start_time: str = Body(None), end_time: str = Body(None),
                               department_id: int = Body(None), out_product: int = Body(None), platform: int = Body(None),
                               chip: int = Body(None), outsourcer_type: int = Body(None)):
    uid, _ = await get_user_by_request(request)
    for sample_id in sample_ids:
        completion = await CompletionStatus.filter(sample_id=sample_id).order_by("-id").first()
        if completion:
            assert completion.is_complete in [28, 29], State.EXPERIMENT_INCOMPLETE
        user_id = None if completion_status != 9 else uid  # 外包
        obj = await CompletionStatus.create(completion_status=completion_status, is_complete=27,
                                            express_company=express_company, express_size=express_size,
                                            outsource_id=outsource_id, start_time=start_time,
                                            department_id=department_id, sample_id=sample_id, user_id=user_id,
                                            end_time=end_time, out_product=out_product, platform=platform, chip=chip,
                                            outsourcer_type=outsourcer_type)
        await InspectOrderSample.filter(pk=sample_id).update(completion_id=obj.id)
    return res()


# 实验流程
@router.post("/receive_completion_status", summary="领取实验流程")
async def receive_completion_status(request: Request, ids: List[int] = Body(..., embed=True)):
    uid, _ = await get_user_by_request(request)
    await CompletionStatus.filter(pk__in=ids).update(user_id=uid)
    return res()


@router.post("/forced_end_sample_order", summary="强制结束任务单")
async def forced_end_sample_order(request: Request, sample_id: int = Body(...), data_type: int = Body(1),
                                  completion_id: int = Body(None), desc: str = Body("")):
    """

    :param sample_id: 样本id
    :param data_type: 1: 强制结束样本单， 2：强制结束实验流程
    :param completion_id:
    :return:
    """
    uid, _ = await get_user_by_request(request)
    user = await get_user_name(uid)
    sample = await InspectOrderSample.filter(pk=sample_id).first()
    order = await InspectOrder.filter(pk=sample.order_id).first()
    if data_type == 1:
        await InspectOrderSample.filter(pk=sample_id).update(is_complete=29)
        await CompletionStatus.filter(id=completion_id).update(is_complete=29, desc=desc)
        content_info = ""
    else:
        await CompletionStatus.filter(id=completion_id).update(is_complete=29, desc=desc)
        completion = await CompletionStatus.filter(id=completion_id).first()
        content_info = await get_dataoption_info(completion.completion_status)
    content = f"""
                {user} 已结束患者：{order.nickname}  的样本编号为：{sample.sample_no} 的{content_info}任务
        """
    await send_email("强制结束任务提醒", content, config.REPORT_SEND_EMAIL, [], uid)
    return res()


@router.post("/submit_data", summary="提交结果数据")
async def submit_data(request: Request, id: int = Form(...), txt_content: str = Form(""),
                      completion_status: int = Form(None), express_company: str = Form(None),
                      express_size: str = Form(""), outsource_id: int = Form(None), start_time: str = Form(None),
                      department_id: int = Form(None), files: List[UploadFile] = File(None),
                      desc: str = Form(""), out_product: int = Form(None), platform: int = Form(None),
                      chip: int = Form(None), end_time: str = Form(None), outsourcer_type: int = Form(None)):
    """
    :param request:
    :param id:  提交数据的id
    :param submit_data:  提交数据, 提取:{"test_kit": "试剂盒", "consistence": "核酸浓度（ng/μL)", "volume": "回溶体积（μL）",
                                       "od260_280": "260/280", "od260_230": "260/230", "nucleic_type": "cDNA",
                                       "extraction_kit": "Magen通用型gDNA", "extraction_kit_batch": "XXX"}
                                建库:{"nucleic_consistence": "核酸浓度", "nucleic_volume": "核酸投入体积（μL）",
                                     "library_consistence": "文库浓度（ng/μL)", "library_volume": "文库体积（μL）",
                                     "peak_plot": "峰图", "library_reagent": "诺唯赞ND627", "library_reagent_batch": "XXX"}
                                捕获:{"library_consistence": "文库浓度（ng/μL)", "library_volume": "文库投入体积（μL）",
                                     "capture_consistence": "捕获产物浓度（ng/μL)", "capture_volume": "捕获产物体积（μL）",
                                     "capture_reagent": "艾吉泰康", "capture_reagent_batch": "XXX",
                                     "capture_probe": "650", "capture_probe_batch": "XXX"}
    :param completion_status:  下阶段流程id
    :param express_company:  快递公司
    :param express_size:  快递单号
    :param outsource_id:  外包商
    :param start_time:  外包开始时间
    :param department_id:  下阶段部门
    :return:
    """
    uid, _ = await get_user_by_request(request)

    if completion_status == 9:  # 外包
        print(f"{express_company=}, {express_size=}, {outsource_id=}, {start_time=}")
        assert all([outsource_id, start_time, end_time]), State.PARAMS_ERROR
    # else:
    #     print(f"{txt_content=}, {department_id=}")
    #     assert all([txt_content, department_id]), State.PARAMS_ERROR
    completion = await CompletionStatus.filter(pk=id).first()
    completion.is_complete = 28
    completion.txt_content = txt_content
    completion.desc = desc
    await completion.save()
    #  下一个流程
    if completion_status:
        obj = await CompletionStatus.create(completion_status=completion_status, express_company=express_company,
                                            express_size=express_size, outsource_id=outsource_id, start_time=start_time,
                                            department_id=department_id, sample_id=completion.sample_id,
                                            out_product=out_product, platform=platform, chip=chip, end_time=end_time,
                                            outsourcer_type=outsourcer_type)
        await InspectOrderSample.filter(pk=completion.sample_id).update(completion_id=obj.id)
    if files:
        for file in files:
            file_id = await save_file(file, uid)
            await CompletionStatusFile.create(data_id=id, file_id=file_id)
    return res()


# 提取
@router.post("/get_all_extract_data", summary="获取所有提取的样本")
async def get_all_extract_data(request: Request):
    """
    :param request:
    :param data_type: 数据类型，1，全部数据， 2：所有未分配的数据 3：我的数据
    :return:
    """
    uid, _ = await get_user_by_request(request)
    body = await request.json()
    # print(f"{body=}")
    page = body.pop("page")
    limit = body.pop("limit")
    search = body.pop("search")
    data_type = body.pop("data_type")
    query = CompletionStatus.filter(is_delete=0, completion_status=6)
    if data_type == 2:
        query = query.filter(user_id__isnull=True)
    elif data_type == 3:
        query = query.filter(user_id=uid)
    if search != "":
        orders = await InspectOrder.filter(Q(nickname__icontains=search) | Q(report_email__icontains=search)).all()
        samples = await InspectOrderSample.filter(Q(sample_no__icontains=search) | Q(order_id__in=[item.pk for item in orders]))
        query = query.filter(sample_id__in=[item.pk for item in samples])
    for key in list(body.keys()):
        if key == "totalResult":
            body.pop("totalResult")
            continue
        if key == "txt_content":
            txt_content = body.pop("txt_content")
            body["txt_content__icontains"] = txt_content
            continue
        if body[key] in [0, "", "-1", 1]:
            if key == "approve_status":
                if str(body[key]) == "-1":
                    body.pop(key)
            else:
                body.pop(key)

    if "sample_type" in list(body.keys()):
        sample_type = body.pop("sample_type")
        s_data = await InspectOrderSample.filter(sample_type=sample_type).all()
        query = query.filter(sample_id__in=[item.pk for item in s_data])
    if "project" in list(body.keys()):
        project = body.pop("project")
        projects = await InspectOrderSample.filter(project_id=project).all()
        query = query.filter(sample_id__in=[item.pk for item in projects])
    query = query.filter(**body)
    total = await query.count()
    data = await query.order_by("-id").offset((page - 1) * limit).limit(limit).values()
    for item in data:
        item["completion_status_info"] = await get_dataoption_info(item["completion_status"])
        item["is_complete_info"] = await get_dataoption_info(item["is_complete"])
        department = await Department.filter(pk=item["department_id"]).first() if item["department_id"] else None
        item["department_info"] = department.name if department else ""
        item["sample_data"] = await get_salple_info(item["sample_id"])
        item["user"] = await get_user_name(item["user_id"]) if item["user_id"] else ""
        item["txt_content"] = eval(item["txt_content"]) if item["txt_content"] != "" else {}
        item["nickname"], item["order_no"] = await get_order_user(item["sample_id"])
    return res(data=dict(data=data, total=total))


# 建库
@router.post("/get_all_building_data", summary="获取所有建库的样本")
async def get_all_building_data(request: Request):
    """
    :param request:
    :param data_type: 数据类型，1，全部数据， 2：所有未分配的数据 3：我的数据
    :return:
    """
    uid, _ = await get_user_by_request(request)
    body = await request.json()
    page = body.pop("page")
    limit = body.pop("limit")
    search = body.pop("search")
    data_type = body.pop("data_type")
    query = CompletionStatus.filter(is_delete=0, completion_status=7)
    if data_type == 2:
        query = query.filter(user_id__isnull=True)
    elif data_type == 3:
        query = query.filter(user_id=uid)
    if search != "":
        orders = await InspectOrder.filter(Q(nickname__icontains=search) | Q(report_email__icontains=search)).all()
        samples = await InspectOrderSample.filter(Q(sample_no__icontains=search) | Q(order_id__in=[item.pk for item in orders]))
        query = query.filter(sample_id__in=[item.pk for item in samples])
    for key in list(body.keys()):
        if key == "totalResult":
            body.pop("totalResult")
            continue
        if body[key] in [0, "", "-1", 1]:
            if key == "approve_status":
                if str(body[key]) == "-1":
                    body.pop(key)
            else:
                body.pop(key)

    if "sample_type" in list(body.keys()):
        sample_type = body.pop("sample_type")
        s_data = await InspectOrderSample.filter(sample_type=sample_type).all()
        query = query.filter(sample_id__in=[item.pk for item in s_data])
    if "project" in list(body.keys()):
        project = body.pop("project")
        projects = await InspectOrderSample.filter(project_id=project).all()
        query = query.filter(sample_id__in=[item.pk for item in projects])
    query = query.filter(**body)
    total = await query.count()
    data = await query.order_by("-id").offset((page - 1) * limit).limit(limit).values()
    for item in data:
        item["completion_status_info"] = await get_dataoption_info(item["completion_status"])
        item["is_complete_info"] = await get_dataoption_info(item["is_complete"])
        department = await Department.filter(pk=item["department_id"]).first() if item["department_id"] else None
        item["department_info"] = department.name if department else ""
        item["sample_data"] = await get_salple_info(item["sample_id"])
        item["user"] = await get_user_name(item["user_id"]) if item["user_id"] else ""
        item["txt_content"] = eval(item["txt_content"]) if item["txt_content"] != "" else {}
        item["nickname"], item["order_no"] = await get_order_user(item["sample_id"])
    return res(data=dict(data=data, total=total))


# 测序
@router.post("/get_all_capture_data", summary="获取所有捕获的样本")
async def get_all_capture_data(request: Request):
    """
    :param request:
    :param data_type: 数据类型，1，全部数据， 2：所有未分配的数据 3：我的数据
    :return:
    """
    uid, _ = await get_user_by_request(request)
    body = await request.json()
    page = body.pop("page")
    limit = body.pop("limit")
    search = body.pop("search")
    data_type = body.pop("data_type")
    query = CompletionStatus.filter(is_delete=0, completion_status=8)
    if data_type == 2:
        query = query.filter(user_id__isnull=True)
    elif data_type == 3:
        query = query.filter(user_id=uid)
    if search != "":
        orders = await InspectOrder.filter(Q(nickname__icontains=search) | Q(report_email__icontains=search)).all()
        samples = await InspectOrderSample.filter(Q(sample_no__icontains=search) |Q(order_id__in=[item.pk for item in orders]))
        query = query.filter(sample_id__in=[item.pk for item in samples])
    for key in list(body.keys()):
        if key == "totalResult":
            body.pop("totalResult")
            continue
        if body[key] in [0, "", "-1", 1]:
            if key == "approve_status":
                if str(body[key]) == "-1":
                    body.pop(key)
            else:
                body.pop(key)

    if "sample_type" in list(body.keys()):
        sample_type = body.pop("sample_type")
        s_data = await InspectOrderSample.filter(sample_type=sample_type).all()
        query = query.filter(sample_id__in=[item.pk for item in s_data])
    if "project" in list(body.keys()):
        project = body.pop("project")
        projects = await InspectOrderSample.filter(project_id=project).all()
        query = query.filter(sample_id__in=[item.pk for item in projects])
    query = query.filter(**body)
    total = await query.count()
    data = await query.order_by("-id").offset((page - 1) * limit).limit(limit).values()
    for item in data:
        item["completion_status_info"] = await get_dataoption_info(item["completion_status"])
        item["is_complete_info"] = await get_dataoption_info(item["is_complete"])
        department = await Department.filter(pk=item["department_id"]).first() if item["department_id"] else None
        item["department_info"] = department.name if department else ""
        item["sample_data"] = await get_salple_info(item["sample_id"])
        item["user"] = await get_user_name(item["user_id"]) if item["user_id"] else ""
        item["txt_content"] = eval(item["txt_content"]) if item["txt_content"] != "" else {}
        item["nickname"], item["order_no"] = await get_order_user(item["sample_id"])
    return res(data=dict(data=data, total=total))


# 外包
@router.post("/get_all_outsource_data", summary="获取所有外包的样本")
async def get_all_outsource_data(request: Request):
    """
    :param request:
    :param data_type: 数据类型，1，全部数据， 2：所有未分配的数据 3：我的数据
    :return:
    """
    uid, _ = await get_user_by_request(request)
    body = await request.json()
    print(f"{body=}")
    page = body.pop("page")
    limit = body.pop("limit")
    search = body.pop("search")
    data_type = body.pop("data_type")
    query = CompletionStatus.filter(is_delete=0, completion_status=9)
    if data_type == 2:
        query = query.filter(user_id__isnull=True)
    elif data_type == 3:
        query = query.filter(user_id=uid)
    if search != "":
        orders = await InspectOrder.filter(Q(nickname__icontains=search) | Q(report_email__icontains=search)).all()
        samples = await InspectOrderSample.filter(Q(sample_no__icontains=search) |Q(order_id__in=[item.pk for item in orders]))
        query = query.filter(sample_id__in=[item.pk for item in samples])
    for key in list(body.keys()):
        if key == "totalResult":
            body.pop("totalResult")
            continue
        if key == "end_time":
            end_time = body.pop("end_time")
            body["end_time__startswith"] = end_time
            continue
        if key == "outsource" and body["outsource"] != 0:
            continue
        if body[key] in [0, "", "-1", 1]:
            if key == "approve_status":
                if str(body[key]) == "-1":
                    body.pop(key)
            else:
                body.pop(key)

    if "sample_type" in list(body.keys()):
        sample_type = body.pop("sample_type")
        s_data = await InspectOrderSample.filter(sample_type=sample_type).all()
        query = query.filter(sample_id__in=[item.pk for item in s_data])
    if "project" in list(body.keys()):
        project = body.pop("project")
        projects = await InspectOrderSample.filter(project_id=project).all()
        query = query.filter(sample_id__in=[item.pk for item in projects])
    print(f"{body=}")
    query = query.filter(**body)
    print(query.sql())
    total = await query.count()
    data = await query.order_by("-id").offset((page - 1) * limit).limit(limit).values()
    for item in data:
        item["completion_status_info"] = await get_dataoption_info(item["completion_status"])
        item["is_complete_info"] = await get_dataoption_info(item["is_complete"])
        department = await Department.filter(pk=item["department_id"]).first() if item["department_id"] else None
        item["department_info"] = department.name if department else ""
        item["sample_data"] = await get_salple_info(item["sample_id"])
        item["user"] = await get_user_name(item["user_id"]) if item["user_id"] else ""
        item["txt_content"] = eval(item["txt_content"]) if item["txt_content"] != "" else {}
        item["nickname"], item["order_no"] = await get_order_user(item["sample_id"])
        item["express_company_info"] = await get_dataoption_info(item["express_company"]) if item["express_company"] else ""
        outsourcer = await OutsourcerInfo.filter(pk=item["outsource_id"]).first() if item["outsource_id"] else None
        item["outsource_info"] = outsourcer.name if outsourcer else ""
        item["start_time"] = str(item["start_time"])[:19] if item["start_time"] else ""
        item["end_time"] = str(item["end_time"])[:19] if item["end_time"] else ""
        item["platform_info"] = await get_dataoption_info(item["platform"]) if item["platform"] else ""
        item["chip_info"] = await get_dataoption_info(item["chip"]) if item["chip"] else ""
        # 捕获探针
        last_probe = await CompletionStatus.filter(sample_id=item["id"], completion_status=8).order_by("-id").first()
        item["capture_probe"] = ""
        if last_probe:
            if last_probe.txt_content:
                item["capture_probe"] = eval(last_probe.txt_content).get("capture_probe")
        item["outsourcer_type_info"] = await get_dataoption_info(item["outsourcer_type"]) if item["outsourcer_type"] else ""
        if item["out_product"]:
            out_product = await OutsourcerProductInfo.filter(pk=item["out_product"]).first()
            item["out_product_info"] = out_product.name
        else:
            item["out_product_info"] = ""
    return res(data=dict(data=data, total=total))


@router.post("/update_outsource_data", summary="修改外包的样本数据")
async def update_outsource_data(request: Request, desc: str = Body(""), express_company: str = Body(""),
                                express_size: str = Body(""), outsource_id: int = Body(...),
                                outsourcer_type: int = Body(...), start_time: str = Body(""), end_time: str = Body(""),
                                out_product: int = Body(...), platform: int = Body(None), chip: int = Body(None),
                                id: int = Body(...)):
    await CompletionStatus.filter(pk=id).update(desc=desc, express_company=express_company, express_size=express_size,
                                                outsource_id=outsource_id, outsourcer_type=outsourcer_type,
                                                start_time=start_time, end_time=end_time, out_product=out_product,
                                                platform=platform, chip=chip)
    return res()


#############
# 实验列表
@router.post("/get_all_not_complete_data", summary="获取所有未完成的样本")
async def get_all_not_complete_data(request: Request):
    uid, _ = await get_user_by_request(request)
    body = await request.json()
    print(f"{body=}")
    page = body.pop("page")
    limit = body.pop("limit")
    search = body.pop("search")
    data_type = body.pop("data_type")
    send_user_id = body.pop("send_user_id")
    query = InspectOrderSample.filter(is_delete=0, is_allocation=1)
    if search != "":
        orders = await InspectOrder.filter(Q(nickname__icontains=search) | Q(report_phone__icontains=search)).all()
        query = query.filter(Q(sample_no__icontains=search) | Q(order_id__in=[item.pk for item in orders]))
    if data_type == 2:
        query = query.filter(user_id=uid)
    if send_user_id:
        orders = await InspectOrder.filter(send_user_id=send_user_id).all()
        query = query.filter(order_id__in=[item.pk for item in orders])
    for key in list(body.keys()):
        if key == "totalResult":
            body.pop("totalResult")
            continue
        if key == "gather_dt":
            gather_dt = body.pop("gather_dt")
            if gather_dt:
                body["gather_dt__icontains"] = gather_dt
            continue
        if key == "charge_dt":
            charge_dt = body.pop("charge_dt")
            if charge_dt:
                body["charge_dt__icontains"] = charge_dt
            continue
        if body[key] in [0, "", "-1", 1]:
            if key == "approve_status":
                if str(body[key]) == "-1":
                    body.pop(key)
            else:
                body.pop(key)

    # if "is_complete" in list(body.keys()):
    #     is_complete = body.pop("is_complete")
    #     s_data = await CompletionStatus.filter(is_complete=is_complete).all()
    #     query = query.filter(id__in=[item.sample_id for item in s_data])
    # if "project" in list(body.keys()):
    #     project = body.pop("project")
    #     projects = await InspectOrderSample.filter(project_id=project).all()
    #     query = query.filter(sample_id__in=[item.pk for item in projects])
    query = query.filter(**body)
    # print(query.sql())
    print(query.sql())
    total = await query.count()
    data = await query.order_by("-id").offset((page - 1) * limit).limit(limit).values()
    for item in data:
        item["sample_type_info"] = await get_dataoption_info(item["sample_type"])
        item["unit_info"] = await get_dataoption_info(item["unit"])
        item["sample_attribute_info"] = await get_dataoption_info(item["sample_attribute"])
        item["gather_dt"] = str(item["gather_dt"])[:10]
        item["deadline_dt"] = str(item["deadline_dt"])[:10]
        item["charge_status_info"] = await get_dataoption_info(item["charge_status"])
        item["charge_dt"] = str(item["charge_dt"])[:10] if item["charge_dt"] else ""
        # 当前实验流程
        item["completion_data"] = await get_completion_status_info_tool(item["completion_id"])
        item["is_complete_info"] = await get_dataoption_info(item["is_complete"])
        project = await ProjectInfo.filter(pk=item["project_id"]).first()
        item["project"] = project.name
        order = await InspectOrder.filter(pk=item["order_id"]).first()
        item["nickname"] = order.nickname
        item["sex"] = order.sex
        item["age"] = order.age
        item["report_phone"] = order.report_phone
        item["user"] = await get_user_name(item["user_id"])
        item["send_user"] = await get_user_name(order.send_user_id)
    return res(data=dict(data=data, total=total))


@router.get("/get_one_not_complete_data", summary="获取单条未完成的样本")
async def get_one_not_complete_data(id: int):
    query = InspectOrderSample.filter(is_delete=0, id=id)
    data = await query.values()
    for item in data:
        item["sample_type_info"] = await get_dataoption_info(item["sample_type"])
        item["unit_info"] = await get_dataoption_info(item["unit"])
        item["sample_attribute_info"] = await get_dataoption_info(item["sample_attribute"])
        item["gather_dt"] = str(item["gather_dt"])[:10]
        item["deadline_dt"] = str(item["deadline_dt"])[:10]
        item["charge_status_info"] = await get_dataoption_info(item["charge_status"])
        item["charge_dt"] = str(item["charge_dt"])[:10] if item["charge_dt"] else ""
        # 当前实验流程
        item["completion_data"] = await get_completion_status_info_tool(item["completion_id"])
        item["is_complete_info"] = await get_dataoption_info(item["is_complete"])
        project = await ProjectInfo.filter(pk=item["project_id"]).first()
        item["project"] = project.name
        order = await InspectOrder.filter(pk=item["order_id"]).first()
        item["nickname"] = order.nickname
        item["sex"] = order.sex
        item["age"] = order.age
        item["report_phone"] = order.report_phone
        item["user"] = await get_user_name(item["user_id"])
    return res(data=data)


@router.get("/get_completion_status_info", summary="获取样本实验详情")
async def get_completion_status_info(sample_id: int):
    data = await CompletionStatus.filter(sample_id=sample_id).order_by("-id").values()
    for item in data:
        txt_content = eval(item["txt_content"]) if item["txt_content"] != "" else {}
        item["txt_content_data"] = txt_content
        item["completion_status_info"] = await get_dataoption_info(item["completion_status"])
        item["is_complete_info"] = await get_dataoption_info(item["is_complete"])
        item["express_company_info"] = await get_dataoption_info(item["express_company"]) if item["express_company"] else ""
        if item["outsource_id"]:
            outsource = await OutsourcerInfo.filter(pk=item["outsource_id"]).first()
        else:
            outsource = None
        item["outsource"] = outsource.name if outsource else ""
        if item["department_id"]:
            department = await Department.filter(pk=item["department_id"]).first()
            item["department"] = department.name
        item["user"] = await get_user_name(item["user_id"])
        item["created_at"] = str(item["created_at"])[:19]
        item["start_time"] = str(item["start_time"])[:19] if item["start_time"] else ""
        item["end_time"] = str(item["end_time"])[:19] if item["end_time"] else ""
        item["platform_info"] = await get_dataoption_info(item["platform"]) if item["platform"] else ""
        item["chip_info"] = await get_dataoption_info(item["chip"]) if item["chip"] else ""
        item["outsourcer_type_info"] = await get_dataoption_info(item["outsourcer_type"]) if item["outsourcer_type"] else ""
        if item["out_product"]:
            out_product = await OutsourcerProductInfo.filter(pk=item["out_product"]).first()
            item["out_product_info"] = out_product.name
        else:
            item["out_product_info"] = ""
        files = await CompletionStatusFile.filter(data_id=item["id"]).all()
        file_query = await FileData.filter(pk__in=[item.file_id for item in files]).values()
        for file_item in file_query:
            file_item["submit"] = await get_user_name(file_item["submit_id"])
            file_item["size"] = calculation_size(int(file_item["size"])) if file_item["size"] else ""
            file_item["created_at"] = str(file_item["created_at"])[:19]
            file_item.pop("file_path")
        item["files_data"] = file_query
    return res(data=data)


@router.get("/get_completion_status_file", summary="获取样本实验流程附件详情")
async def get_completion_status_file(data_id: int, search: str = "", page: int = 1, limit: int = 10):
    files = await CompletionStatusFile.filter(data_id=data_id).all()

    query = FileData.filter(pk__in=[item.file_id for item in files], name__icontains=search)
    total = await query.count()
    data = await query.offset((page - 1) * limit).limit(limit).values()
    for file_item in data:
        file_item["submit"] = await get_user_name(file_item["submit_id"])
        file_item["size"] = calculation_size(int(file_item["size"])) if file_item["size"] else ""
        file_item["created_at"] = str(file_item["created_at"])[:19]
        file_item.pop("file_path")
    return res(data=dict(data=data, total=total))


# 解读
@router.post("/get_all_sample_interpreting", summary="获取所有的解读数据")
async def get_all_sample_interpreting(request: Request):
    """
    :param request:
    :param data_type: 数据类型，1，全部数据， 2, 我的解读数据， 3，我的审核数据
    :param approve_status: 审核状态，-2：全部，-1：待分配： 0：待解读， 1：待审核， 2：已审核
    :return:
    """
    uid, _ = await get_user_by_request(request)
    body = await request.json()
    page = body.pop("page")
    limit = body.pop("limit")
    search = body.pop("search")
    data_type = body.pop("data_type")
    approve_status = body.pop("approve_status")
    interpret_id = body.pop("interpret_id")
    send_user_id = body.pop("send_user_id")
    query = InspectOrderSample.filter(is_delete=0, is_allocation=1, is_interpret=1).filter(~Q(is_complete=29))
    if search != "":
        orders = await InspectOrder.filter(Q(nickname__icontains=search) | Q(report_phone__icontains=search)).all()
        query = query.filter(Q(sample_no__icontains=search) | Q(order_id__in=[item.pk for item in orders]))
    if data_type == 2:  # 我的
        interpretings = await SampleInterpreting.filter(interpret_id=uid).all()
        query = query.filter(pk__in=[item.sample_id for item in interpretings])
    if data_type == 3:  # 我的
        interpretings = await SampleInterpreting.filter(approve_id=uid).all()
        query = query.filter(pk__in=[item.sample_id for item in interpretings])
    if str(approve_status) == "-2":
        pass
    elif str(approve_status) == "-1":
        interpretings = await SampleInterpreting.filter().all()
        # print(f"{interpretings=}")
        if interpretings:
            query = query.filter(pk__not_in=[item.sample_id for item in interpretings])
    else:
        interpretings = await SampleInterpreting.filter(approve_status=approve_status).all()
        query = query.filter(pk__in=[item.sample_id for item in interpretings])
    if interpret_id:
        interpretings = await SampleInterpreting.filter(interpret_id=interpret_id).all()
        query = query.filter(pk__in=[item.sample_id for item in interpretings])
    if send_user_id:  # 销售id
        orders = await InspectOrder.filter(send_user_id=send_user_id).all()
        query = query.filter(order_id__in=[item.pk for item in orders])
    for key in list(body.keys()):
        if key == "totalResult":
            body.pop("totalResult")
            continue
        if key == "deadline_dt":
            deadline_dt = body.pop("deadline_dt")
            body["deadline_dt__icontains"] = deadline_dt
            continue
        # if key == "deadline_dt":
        #     deadline_dt_value = body.pop("deadline_dt")
        #     continue
        if body[key] in [0, "", "-1", 1]:
            if key == "approve_status":
                if str(body[key]) == "-1":
                    body.pop(key)
            else:
                body.pop(key)
    if "sample_type" in list(body.keys()):
        sample_type = body.pop("sample_type")
        query = query.filter(sample_type=sample_type)
    if "project" in list(body.keys()):
        project = body.pop("project")
        query = query.filter(project_id=project)
    query = query.filter(**body)
    desc_list = []
    # if deadline_dt_value == 1:
    #     desc_list.append("deadline_dt")
    # elif deadline_dt_value == 2:
    #     desc_list.append("-deadline_dt")
    desc_list = desc_list or ["-id"]
    total = await query.count()
    data = await query.order_by(*desc_list).offset((page - 1) * limit).limit(limit).values()
    now = datetime.datetime.now()
    valid_time = now + timedelta(days=1)
    valid_time = str(valid_time)[:10]
    for item in data:
        item["sample_type_info"] = await get_dataoption_info(item["sample_type"])
        item["unit_info"] = await get_dataoption_info(item["unit"])
        item["sample_attribute_info"] = await get_dataoption_info(item["sample_attribute"])
        item["is_compare_info"] = await get_dataoption_info(item["is_compare"])
        item["gather_dt"] = str(item["gather_dt"])[:10]
        item["gather_dt_type"] = 0
        item["deadline_dt"] = str(item["deadline_dt"])[:10]
        item["charge_status_info"] = await get_dataoption_info(item["charge_status"])
        item["charge_dt"] = str(item["charge_dt"])[:10] if item["charge_dt"] else ""
        item["deadline_dt"] = str(item["deadline_dt"])[:10] if item["deadline_dt"] else ""
        bioinformatics_data = await get_bioinformatics_data(item["id"])
        item["dna_total"] = bioinformatics_data.get("dna_total", "")
        item["library_total"] = bioinformatics_data.get("library_total")
        # 当前实验流程
        item["completion_data"] = await get_completion_status_info_tool(item["completion_id"])
        item["is_complete_info"] = await get_dataoption_info(item["is_complete"])
        project = await ProjectInfo.filter(pk=item["project_id"]).first()
        item["project"] = project.name
        item["project_info"] = await get_prodcut_level(item["project_id"], product_info=[])
        item["capture_probe"] = project.illustrate
        order = await InspectOrder.filter(pk=item["order_id"]).first()
        item["nickname"] = order.nickname
        item["sex"] = order.sex
        if item["sex"] == 1:
            item["sex_info"] = "男"
        elif item["sex"] == 2:
            item["sex_info"] = "女"
        else:
            item["sex_info"] = "未知"
        item["age"] = order.age
        item["hospital"] = order.hospital
        item["visiting_department"] = order.visiting_department
        item["doctor"] = order.doctor
        item["hospital_num"] = order.hospital_num
        item["specific"] = order.specific
        item["cancer_species"] = await get_dataoption_info(order.cancer_species)
        item["report_phone"] = order.report_phone
        item["user"] = await get_user_name(order.user_id)
        item["send_user"] = await get_user_name(order.send_user_id)
        item["send_user_id"] = order.send_user_id
        item["is_urgent_info"] = await get_dataoption_info(order.is_urgent)
        # # 外包
        # outsource = await CompletionStatus.filter(sample_id=item["id"], completion_status=9).order_by("-id").first()
        # item["capture_probe"] = ""
        # if outsource:
        #     outsource_info = await OutsourcerInfo.filter(id=outsource.outsource_id).first()
        #     item["capture_probe"] = outsource_info.name if outsource_info else ""
        interpret = await SampleInterpreting.filter(sample_id=item["id"]).first()
        if interpret:
            item["interpret_id"] = interpret.id
            item["interpret"] = await get_user_name(interpret.interpret_id) if interpret.interpret_id else ""
            item["interpret_at"] = str(interpret.interpret_at)[:19] if interpret.interpret_at else ""
            item["approve"] = await get_user_name(interpret.approve_id) if interpret.approve_id else ""
            item["approve_at"] = str(interpret.approve_at)[:19] if interpret.approve_at else ""
            item["approve_desc"] = interpret.approve_desc
            item["interpret_desc"] = interpret.desc
            if interpret.approve_status == 0:
                item["approve_status_info"] = "待解读"
            elif interpret.approve_status == 1:
                item["approve_status_info"] = "待审核"
            elif interpret.approve_status == 2:
                item["approve_status_info"] = "已审核"
            elif interpret.approve_status == 3:
                item["approve_status_info"] = "已拒绝"
            else:
                item["approve_status_info"] = "未知"
            item["result_info"] = eval(str(interpret.result).replace(":null", ':""').replace(":nan", ':""')) if interpret.result else []
            for r_item in item["result_info"]:
                r_item["info6"] = convert_percentage(r_item["info6"]) if is_number(r_item["info6"]) else r_item["info6"]
                r_item["info17"] = convert_percentage(r_item["info17"])
            if interpret.approve_status in [0, 1] and item["deadline_dt"] <= valid_time:
                item["gather_dt_type"] = 1
        else:
            item["interpret_id"] = None
            item["interpret"] = ""
            item["interpret_at"] = ""
            item["approve"] = ""
            item["approve_at"] = ""
            item["approve_desc"] = ""
            item["approve_status_info"] = "待分配"
            item["result_info"] = []
            item["interpret_desc"] = ""
            if item["deadline_dt"] <= valid_time:
                item["gather_dt_type"] = 1
        bio_data = await get_bio_info(item["id"])
        item["bio_data"] = bio_data
    return res(data=dict(data=data, total=total))


@router.post("/allocation_sample_interpreting", summary="分配解读数据")
async def allocation_sample_interpreting(samples_ids: List[int] = Body(...), interpret_id: int = Body(...),
                                         approve_id: int = Body(...)):
    for item in samples_ids:
        interpret = await SampleInterpreting.filter(sample_id=item).first()
        if interpret:
            interpret.interpret_id = interpret_id
            interpret.approve_id = approve_id
            await interpret.save()
        else:
            await SampleInterpreting.create(sample_id=item, interpret_id=interpret_id, approve_id=approve_id)
    return res()


@router.post("/sumbit_sample_interpreting", summary="提交解读报告")
async def sumbit_sample_interpreting(request: Request, sample_id: int = Body(...),
                                     desc: str = Body(""),  result: str = Body(...)):

    uid, _ = await get_user_by_request(request)
    interpret = await SampleInterpreting.filter(sample_id=sample_id).first()
    if interpret.interpret_id != uid:
        raise HTTPException(status_code=500, detail="该数据无提交权限！")
    interpret.approve_status = 1
    interpret.desc = desc
    interpret.result = result
    interpret.interpret_at = datetime.datetime.now()
    await interpret.save()
    return res()


@router.post("/approve_sample_interpreting", summary="审核解读报告")
async def approve_sample_interpreting(request: Request, id: int = Form(...), desc: str = Form(""),
                                      files: List[UploadFile] = File(None), result: str = Form(...),
                                      approve_desc: str = Form(""), approve_status: int = Form(2)):
    """
    :param request:
    :param id:
    :param approve_status:
    :param desc:
    :param files:
    :param result: 提交结果，[{"interpret_result": "阴性", "gene_variation"："xxxxxxxx", "gene_variation_update": "是",
                            "other_gene_variation": "xxxxxx", "other_gene_variation_update": "是" },]
    :return:
    """
    uid, _ = await get_user_by_request(request)
    interpret = await SampleInterpreting.filter(id=id).first()
    if interpret.approve_id != uid:
        raise HTTPException(status_code=500, detail="该数据无审核权限！")
    result = str(result).replace(":null", ':""').replace(":nan", ':""')
    interpret.approve_status = approve_status
    interpret.approve_desc = approve_desc
    interpret.desc = desc
    interpret.result = result
    interpret.approve_at = datetime.datetime.now()
    await interpret.save()
    if files:
        for file in files:
            file_id = await save_file(file, uid)
            # print(f"{file_id=}")
            await SampleInterpretingFile.create(data_id=interpret.id, file_id=file_id)
    # 同步数据库
    # print(f"{approve_status=}")
    if approve_status == 2:  # 审核通过
        sample = await InspectOrderSample.filter(pk=interpret.sample_id).first()
        order = await InspectOrder.filter(id=sample.order_id).first()
        content = f"""
                    患者：{order.nickname}  的样本编号为：{sample.sample_no} 的样本的解读报告已审核完成，请及时发送报告！
            """
        await send_email("解读数据完成", content, config.REPORT_SEND_EMAIL, [], uid)
        await SampleReportSendLog.create(sample_id=interpret.sample_id)
        await InterpretingDataBase.filter(interpreting_id=id).delete()
        database = eval(result)
        for item in database:
            item["sample_id"] = sample.id
            item["interpreting_id"] = id
            item["order_id"] = order.id
            # print(f"{item=}")
            await InterpretingDataBase.create(**item)
    return res()


@router.get("/get_sample_interpreting_file", summary="获取解读报告附件详情")
async def get_sample_interpreting_file(sample_id: int, search: str = "", page: int = 1, limit: int = 10):
    interpret = await SampleInterpreting.filter(id=sample_id).first()
    if interpret:
        files = await SampleInterpretingFile.filter(data_id=interpret.id).all()

        query = FileData.filter(pk__in=[item.file_id for item in files], name__icontains=search)
        total = await query.count()
        data = await query.offset((page - 1) * limit).limit(limit).values()
        for file_item in data:
            file_item["submit"] = await get_user_name(file_item["submit_id"])
            file_item["size"] = calculation_size(int(file_item["size"])) if file_item["size"] else ""
            file_item["created_at"] = str(file_item["created_at"])[:19]
            # file_item.pop("file_path")
        return res(data=dict(data=data, total=total))
    return res()


# 样本下单
@router.post("/sample_place_order", summary="样本下单")
async def sample_place_order(ids: List[int] = Body(...), document_type: int = Body(133), is_interpret: int = Body(1),
                             is_bioinformatics: int = Body(1)):
    await InspectOrderSample.filter(pk__in=ids).update(is_allocation=1, document_type=document_type,
                                                       is_interpret=is_interpret, is_bioinformatics=is_bioinformatics)
    return res()


@router.post("/get_sample_place_order_data", summary="获取可以下单的样本数据")
async def get_sample_place_order_data(request: Request):
    uid, _ = await get_user_by_request(request)
    body = await request.json()
    page = body.pop("page")
    limit = body.pop("limit")
    search = body.pop("search")
    query = InspectOrderSample.filter(is_delete=0, is_allocation=2)
    if search != "":
        orders = await InspectOrder.filter(Q(nickname__icontains=search) | Q(report_phone__icontains=search)).all()
        query = query.filter(Q(sample_no__icontains=search) | Q(order_id__in=[item.pk for item in orders]))
    query = query.filter(**body)
    total = await query.count()
    data = await query.order_by("-id").offset((page - 1) * limit).limit(limit).values()
    for item in data:
        item["sample_type_info"] = await get_dataoption_info(item["sample_type"])
        item["unit_info"] = await get_dataoption_info(item["unit"])
        item["sample_attribute_info"] = await get_dataoption_info(item["sample_attribute"])
        item["gather_dt"] = str(item["gather_dt"])[:10]
        item["deadline_dt"] = str(item["deadline_dt"])[:10]
        item["charge_status_info"] = await get_dataoption_info(item["charge_status"])
        item["charge_dt"] = str(item["charge_dt"])[:10] if item["charge_dt"] else ""
        # 当前实验流程
        item["completion_data"] = await get_completion_status_info_tool(item["completion_id"])
        item["is_complete_info"] = await get_dataoption_info(item["is_complete"])
        project = await ProjectInfo.filter(pk=item["project_id"]).first()
        item["project"] = project.name
        item["project_info"] = await get_prodcut_level(item["project_id"], product_info=[])
        order = await InspectOrder.filter(pk=item["order_id"]).first()
        item["nickname"] = order.nickname
        item["sex"] = order.sex
        item["age"] = order.age
        item["report_phone"] = order.report_phone
        item["user"] = await get_user_name(item["user_id"])
    return res(data=dict(data=data, total=total))


# 生信
@router.post("/get_all_sample_bioinformatics", summary="获取所有的生信数据")
async def get_all_sample_bioinformatics(request: Request):
    """
    :param request:
    :param data_type: 数据类型，1，全部数据， 2, 我的数据
    :return:
    """
    uid, _ = await get_user_by_request(request)
    body = await request.json()
    # print(f"{body=}")
    page = body.pop("page")
    limit = body.pop("limit")
    search = body.pop("search")
    data_type = body.pop("data_type")
    project_id = body.pop("project_id")
    approve_status = body.pop("approve_status")
    query = InspectOrderSample.filter(is_delete=0, is_allocation=1, is_bioinformatics=1).filter(~Q(is_complete=29))
    if search != "":
        orders = await InspectOrder.filter(Q(nickname__icontains=search) | Q(report_phone__icontains=search)).all()
        query = query.filter(Q(sample_no__icontains=search) | Q(order_id__in=[item.pk for item in orders]))
    if project_id:
        query = query.filter(project_id=project_id)
    if data_type == 2:  # 我的
        bioinformatics = await SampleBioInformatics.filter(Q(execute_id=uid) | Q(approve_id=uid)).all()
        query = query.filter(pk__in=[item.sample_id for item in bioinformatics])
    if str(approve_status) == "-2":
        pass
    elif str(approve_status) == "-1":
        interpretings = await SampleBioInformatics.filter().all()
        # print(f"{interpretings=}")
        if interpretings:
            query = query.filter(pk__not_in=[item.sample_id for item in interpretings])
    else:
        interpretings = await SampleBioInformatics.filter(approve_status=approve_status).all()
        query = query.filter(pk__in=[item.sample_id for item in interpretings])
    for key in list(body.keys()):
        if key == "totalResult":
            body.pop("totalResult")
            continue
        if key == "gather_dt":
            gather_dt_value = body.pop("gather_dt")
            continue
        if body[key] in [0, "", "-1"]:
            if key == "approve_status":
                if str(body[key]) == "-1":
                    body.pop(key)
            else:
                body.pop(key)
    desc_list = []
    if gather_dt_value == 1:
        desc_list.append("gather_dt")
    elif gather_dt_value == 2:
        desc_list.append("-gather_dt")
    desc_list = desc_list or ["-id"]
    query = query.filter(**body)
    # print(query.sql())
    total = await query.count()
    data = await query.order_by(*desc_list).offset((page - 1) * limit).limit(limit).values()
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
        last_data = await CompletionStatus.filter(sample_id=item["id"], completion_status=6).order_by("-id").first()
        item["nucleic_type"] = ""
        if last_data:
            if last_data.txt_content:
                item["nucleic_type"] = eval(last_data.txt_content).get("nucleic_type")
        # # 捕获探针
        # last_probe = await CompletionStatus.filter(sample_id=item["id"], completion_status=8).order_by("-id").first()
        # item["capture_probe"] = ""
        # if last_probe:
        #     if last_probe.txt_content:
        #         item["capture_probe"] = eval(last_probe.txt_content).get("capture_probe")
        item["is_complete_info"] = await get_dataoption_info(item["is_complete"])
        project = await ProjectInfo.filter(pk=item["project_id"]).first()
        item["project"] = project.name
        item["capture_probe"] = project.illustrate
        item["project_info"] = await get_prodcut_level(item["project_id"], product_info=[])
        order = await InspectOrder.filter(pk=item["order_id"]).first()
        item["nickname"] = order.nickname
        item["sex"] = "男" if order.sex == 1 else "女"
        item["age"] = order.age
        item["is_urgent_info"] = await get_dataoption_info(order.is_urgent)
        item["report_phone"] = order.report_phone
        item["user"] = await get_user_name(item["user_id"])
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


@router.post("/allocation_sample_bioinformatics", summary="分配生信数据")
async def allocation_sample_bioinformatics(samples_ids: List[int] = Body(...), execute_id: int = Body(...)):
    for item in samples_ids:
        data = await SampleBioInformatics.filter(sample_id=item).first()
        if data:
            data.interpret_id = execute_id
            await data.save()
        else:
            await SampleBioInformatics.create(sample_id=item, execute_id=execute_id)
    return res()


@router.post("/sumbit_sample_bioinformatics", summary="提交生信报告")
async def sumbit_sample_bioinformatics(request: Request, sample_id: int = Form(...), files: List[UploadFile] = File(None),
                                       approve_id: int = Form(...), result: str = Form("")):
    uid, _ = await get_user_by_request(request)
    data = await SampleBioInformatics.filter(sample_id=sample_id).first()
    if data.execute_id != uid:
        raise HTTPException(status_code=500, detail="该数据无提交权限！")
    if files:
        for file in files:
            file_id = await save_file(file, uid)
            # print(f"{file_id=}")
            await SampleBioInformaticsFile.create(data_id=data.id, file_id=file_id)
    data.approve_id = approve_id
    data.approve_status = 3
    data.interpret_at = datetime.datetime.now()
    data.result = result
    await data.save()
    return res()


@router.post("/approve_sample_bioinformatics", summary="审核生信报告")
async def approve_sample_bioinformatics(request: Request, id: int = Body(...), approve_status: int = Body(...),
                                        desc: str = Body("")):
    uid, _ = await get_user_by_request(request)
    data = await SampleBioInformatics.filter(id=id).first()
    if data.approve_id != uid:
        raise HTTPException(status_code=500, detail="该数据无审核权限！")
    data.approve_status = approve_status
    data.approve_desc = desc
    data.approve_at = datetime.datetime.now()
    await data.save()
    return res()


@router.get("/get_sample_bioinformatics_file", summary="获取生信报告附件详情")
async def get_sample_bioinformatics_file(sample_id: int, search: str = "", page: int = 1, limit: int = 10):
    bio_data = await SampleBioInformatics.filter(sample_id=sample_id).first()
    if bio_data:
        files = await SampleBioInformaticsFile.filter(data_id=bio_data.id).all()

        query = FileData.filter(pk__in=[item.file_id for item in files], name__icontains=search)
        total = await query.count()
        data = await query.offset((page - 1) * limit).limit(limit).values()
        for file_item in data:
            file_item["submit"] = await get_user_name(file_item["submit_id"])
            file_item["size"] = calculation_size(int(file_item["size"])) if file_item["size"] else ""
            file_item["created_at"] = str(file_item["created_at"])[:19]
            file_item.pop("file_path")
        return res(data=dict(data=data, total=total, result=bio_data.result))
    return res()


# 报告管理页面
@router.post("/get_sample_report_send_log", summary="获取报告发送页面数据")
async def get_sample_report_send_log(request: Request):
    body = await request.json()
    page = body.pop("page")
    limit = body.pop("limit")
    search = body.pop("search")
    query = SampleReportSendLog.filter(is_delete=0)
    if search != "":
        orders = await InspectOrder.filter(Q(nickname__icontains=search) | Q(report_phone__icontains=search)).all()
        orders_samples = await InspectOrderSample.filter(order_id__in=[item.pk for item in orders]).all()
        query = query.filter(sample_id__in=[item.pk for item in orders_samples])
    query = query.filter(**body)
    total = await query.count()
    data = await query.order_by("-id").offset((page - 1) * limit).limit(limit).values()
    for item in data:
        sample = await InspectOrderSample.filter(pk=item["sample_id"]).first()
        order = await InspectOrder.filter(pk=sample.order_id).first()
        interpreting = await SampleInterpreting.filter(sample_id=item["sample_id"]).first()
        item["interpreting_id"] = interpreting.pk
        item["nickname"] = order.nickname
        item["sample_no"] = sample.sample_no
        item["report_receive"] = order.report_receive
        item["report_phone"] = order.report_phone
        item["report_email"] = order.report_email
        item["report_addr"] = order.report_addr
        item["sample_type"] = await get_dataoption_info(sample.sample_type)
        item["sample_attribute"] = await get_dataoption_info(sample.sample_attribute)
        item["number"] = sample.number
        item["unit"] = await get_dataoption_info(sample.unit)
        item["gather_dt"] = str(sample.gather_dt)[:19] if sample.gather_dt else ""
        item["send_at"] = str(item["send_at"])[:19] if item["send_at"] else ""
        item["mail_at"] = str(item["mail_at"])[:19] if item["mail_at"] else ""
        item["is_return"] = await get_dataoption_info(item["is_return"])
        item["is_email_send"] = await get_dataoption_info(item["is_email_send"])
    return res(data=dict(data=data, total=total))


@router.post("/update_sample_report_log", summary="修改报告发送数据")
async def update_sample_report_log(request: Request, send_at: str = Body(None), receive: str = Body(""),
                                   phone: str = Body(""), mail_address: str = Body(""), mail_at: str = Body(None),
                                   express_company: str = Body(""), express_no: str = Body(""),
                                   invoice_no: str = Body(""), is_return: int = Body(2), is_email_send: int = Body(2),
                                   desc: str = Body(""), id: int = Body(...), content: str = Body("")):
    uid, _ = await get_user_by_request(request)
    mail_at = mail_at if mail_at else datetime.datetime.now()
    await SampleReportSendLog.filter(pk=id).update(send_at=send_at, receive=receive, phone=phone, mail_at=mail_at,
                                                   mail_address=mail_address,  express_company=express_company,
                                                   express_no=express_no, invoice_no=invoice_no, is_return=is_return,
                                                   is_email_send=is_email_send, desc=desc, user_id=uid)
    if is_email_send == 1:  # 需要发送邮件
        assert all([content, receive]), State.PARAMS_ERROR
        receives = [receive]
        log = await SampleReportSendLog.filter(pk=id).first()
        interpret = await SampleInterpreting.filter(sample_id=log.sample_id).first()
        in_files = await SampleInterpretingFile.filter(data_id=interpret.pk).all()
        files = await FileData.filter(pk__in=[item.file_id for item in in_files]).all()
        files_path = [item.file_path for item in files]
        await send_email("检测报告发送", content, receives, files_path, uid)
    return res()


@router.post("/read_interpret_excel", summary="读取解读结果表格数据")
async def read_interpret_excel(file: UploadFile = File(...)):
    print("解读结果文件")
    content = await file.read()
    # data = pd.read_excel(content, keep_default_na=False)
    data = pd.read_excel(content)
    columns = data.columns.values.tolist()
    data_list = data.values.tolist()
    # print(f"{data_list=}")
    # print(f"{columns=}")
    if columns != ["临床诊断", "阴性/阳性/无",	"基因",	"染色体位置", "变异信息", "突变丰度/拷贝数/杂合性", "变异等级",
                   "OMIM/相关疾病/遗传方式", "临床意义（诊断/预后/治疗）", "敏感/正相关", "不敏感/负相关", "不一致", "解读详情",
                   "疾病介绍", "免疫治疗相关类型（正相关/负相关/超进展）", "人类白细胞抗原(HLA)", "是否与肿瘤遗传相关基因变异（是或否）",
                   "MSI score", "TMB score", "PD-L1 score", "分子分型（TCGA项目）", "是否新解读", "MMR检测结果 (pMMR/dMMR)"]:
        raise HTTPException(status_code=500, detail="提交表格模板不对")
    data_columns = [f"info{str(item+1)}" for item in range(len(columns))]
    excel_data = [[str(item_i) if any([str(item_i) not in ["nan", "null"], not item_i]) else "" for item_i in item] for item in data_list]
    # print(f"{excel_data=}")
    r_data = [dict(zip(data_columns, item))for item in excel_data]
    return res(data=r_data)


@router.get("/down_interpret_excel_model", summary="下载解读结果表格模板")
async def down_interpret_excel_model():
    return FileResponse(path=os.path.join("file", "model", "解读结果提交模板.xlsx"), filename="解读结果提交模板.xlsx")


@router.get("/down_batch_import_interpret_excel_model", summary="下载批量解读结果表格模板")
async def down_batch_import_interpret_excel_model():
    return FileResponse(path=os.path.join("file", "model", "批量解读结果导入模版.xlsx"), filename="批量解读结果导入模版.xlsx")


@router.post("/batch_import_interpret_excel", summary="批量解读结果表格数据")
async def batch_import_interpret_excel(reuqest: Request, file: UploadFile = File(...), approve_id: int = Form(...)):
    uid, _ = await get_user_by_request(reuqest)
    print("解读结果文件")
    content = await file.read()
    data = pd.read_excel(content)
    columns = data.columns.values.tolist()
    data_list = data.values.tolist()
    # print(f"{data_list=}")
    print(columns[1:])
    if columns[1:] != ["临床诊断", "阴性/阳性/无",	"基因",	"染色体位置", "变异信息", "突变丰度/拷贝数/杂合性", "变异等级",
                   "OMIM/相关疾病/遗传方式", "临床意义（诊断/预后/治疗）", "敏感/正相关", "不敏感/负相关", "不一致", "解读详情",
                   "疾病介绍", "免疫治疗相关类型（正相关/负相关/超进展）", "人类白细胞抗原(HLA)", "是否与肿瘤遗传相关基因变异（是或否）",
                   "MSI score", "TMB score", "PD-L1 score", "分子分型（TCGA项目）", "是否新解读", "MMR检测结果 (pMMR/dMMR)"]:
        raise HTTPException(status_code=500, detail="提交表格模板不对")
    data_columns = [f"info{str(item+1)}" for item in range(len(columns[1:]))]
    integration_dict = {}
    for item in data_list:
        sample_no = item[0]
        excel_data = [str(item_i) if str(item_i) not in ["nan", "null"] else "" for item_i in item[1:]]
        excel_data = dict(zip(data_columns, excel_data))
        if sample_no in integration_dict.keys():
            integration_dict[sample_no] += [excel_data]
        else:
            integration_dict[sample_no] = [excel_data]
    for key, value in integration_dict.items():
        sample = await InspectOrderSample.filter(sample_no=key).first()
        if not sample:
            continue
        interpreting = await SampleInterpreting.filter(sample_id=sample.id).first()
        if interpreting:
            interpreting.interpret_at = datetime.datetime.now()
            interpreting.approve_id = approve_id
            interpreting.approve_status = 1
            interpreting.result = str(value)
            await interpreting.save()
        else:
            await SampleInterpreting.create(interpret_id=uid, interpret_at=datetime.datetime.now(),
                                            approve_id=approve_id, approve_status=1, result=str(value),
                                            sample_id=sample.id)

    return res()


@router.post("/get_interpreting_database", summary="解读数据库")
async def get_interpreting_database(request: Request):
    body = await request.json()
    print(f"{body=}")
    search = body.pop("search")
    page = body.pop("page")
    limit = body.pop("limit")
    send_user_id = body.pop("send_user_id")  # 销售
    nickname = body.pop("nickname")
    specific = body.pop("specific")
    project_id = body.pop("project_id")
    sample_type = body.pop("sample_type")
    # deadline_dt_value = body.pop("deadline_dt")
    query = InterpretingDataBase.filter()
    if send_user_id:
        orders = await InspectOrder.filter(send_user_id=send_user_id).all()
        query = query.filter(order_id__in=[item.pk for item in orders])
    if nickname:
        orders = await InspectOrder.filter(nickname__icontains=nickname).all()
        query = query.filter(order_id__in=[item.pk for item in orders])
    if specific:
        orders = await InspectOrder.filter(specific__icontains=specific).all()
        query = query.filter(order_id__in=[item.pk for item in orders])
    if project_id:
        samples = await InspectOrderSample.filter(project_id=project_id).all()
        query = query.filter(sample_id__in=[item.pk for item in samples])
    if sample_type:
        samples = await InspectOrderSample.filter(sample_type=sample_type).all()
        query = query.filter(sample_id__in=[item.pk for item in samples])
    request_data = {}
    print(f"{body=}")
    for key, value in body.items():
        if str(key).startswith("info") and value != "":
            request_data[f"{key}__icontains"] = value
    print(f"{request_data=}")
    desc_list = []
    # if deadline_dt_value == 1:
    #     desc_list.append("deadline_dt")
    # elif deadline_dt_value == 2:
    #     desc_list.append("-deadline_dt")
    desc_list = desc_list or ["-id"]
    query = query.filter(**request_data)
    data = await query.order_by(*desc_list).offset((page - 1) * limit).limit(limit).values()
    total = await query.count()
    for item in data:
        order = await InspectOrder.filter(pk=item["order_id"]).first()
        sample = await InspectOrderSample.filter(pk=item["sample_id"]).first()
        interpreting = await SampleInterpreting.filter(pk=item["interpreting_id"]).first()
        project = await ProjectInfo.filter(pk=sample.project_id).first()
        item["project"] = project.name
        item["sample_no"] = sample.sample_no
        item["remind_dt"] = str(sample.remind_dt)[:19] if sample.remind_dt else ""
        item["deadline_dt"] = str(sample.deadline_dt)[:19] if sample.deadline_dt else ""
        item["sample_type"] = await get_dataoption_info(sample.sample_type)
        item["nickname"] = order.nickname
        item["cancer_species"] = await get_dataoption_info(order.cancer_species)
        item["specific"] = order.specific
        item["age"] = order.age
        item["send_user"] = await get_user_name(order.send_user_id)
        if order.sex == 1:
            item["sex_info"] = "男"
        elif order.sex == 2:
            item["sex_info"] = "女"
        else:
            item["sex_info"] = "未知"
        item["interpret"] = await get_user_name(interpreting.interpret_id)
        item["approve"] = await get_user_name(interpreting.approve_id)
        item["approve_at"] = str(interpreting.approve_at)[:19] if interpreting.approve_at else ""
        if interpreting.approve_status == 0:
            item["approve_status_info"] = "待解读"
        elif interpreting.approve_status == 1:
            item["approve_status_info"] = "待审核"
        elif interpreting.approve_status == 2:
            item["approve_status_info"] = "已审核"
        elif interpreting.approve_status == 3:
            item["approve_status_info"] = "已拒绝"
        else:
            item["approve_status_info"] = "未知"
        item["info6"] = convert_percentage(item["info6"]) if is_number(item["info6"]) else item["info6"]
        item["info17"] = convert_percentage(item["info17"])
        # item["info18"] = convert_percentage(item["info18"])
        # item["info19"] = convert_percentage(item["info19"])
        # if is_number(item["info6"]):
        #     item["info6"] = f"{round(float(item['info6']) * 100, 2)}%"
        # if "%" in item["info6"]:
        #     item["info6"] = "{}%".format(round(float(str(item["info6"]).replace("%", "")), 2))
    return res(data=dict(data=data, total=total))


# @router.get("/get_interpreting_database", summary="解读数据库")
# async def get_interpreting_database(search: str = "", page: int = 1, limit: int = 10):
#     query = InterpretingDataBase.filter()
#     if search:
#         orders = await InspectOrder.filter(Q(nickname__icontains=search) | Q(report_phone__icontains=search)).all()
#         samples = await InspectOrderSample.filter(sample_no__icontains=search).all()
#         query = query.filter(Q(sample_id__in=[item.pk for item in samples]) |
#                              Q(order_id__in=[item.pk for item in orders]) |
#                              Q(info1__icontains=search) | Q(info2__icontains=search) | Q(info3__icontains=search) |
#                              Q(info4__icontains=search) | Q(info5__icontains=search) | Q(info6__icontains=search) |
#                              Q(info7__icontains=search) | Q(info8__icontains=search) | Q(info9__icontains=search) |
#                              Q(info10__icontains=search) | Q(info11__icontains=search) | Q(info12__icontains=search) |
#                              Q(info13__icontains=search) | Q(info14__icontains=search) | Q(info15__icontains=search) |
#                              Q(info16__icontains=search) | Q(info17__icontains=search) | Q(info18__icontains=search) |
#                              Q(info19__icontains=search) | Q(info20__icontains=search) | Q(info21__icontains=search) |
#                              Q(info22__icontains=search)
#                              )
#     data = await query.offset((page - 1) * limit).limit(limit).values()
#     total = await query.count()
#     for item in data:
#         order = await InspectOrder.filter(pk=item["order_id"]).first()
#         sample = await InspectOrderSample.filter(pk=item["sample_id"]).first()
#         interpreting = await SampleInterpreting.filter(pk=item["interpreting_id"]).first()
#         project = await ProjectInfo.filter(pk=sample.project_id).first()
#         item["project"] = project.name
#         item["sample_no"] = sample.sample_no
#         item["remind_dt"] = str(sample.remind_dt)[:19] if sample.remind_dt else ""
#         item["sample_type"] = await get_dataoption_info(sample.sample_type)
#         item["nickname"] = order.nickname
#         item["cancer_species"] = await get_dataoption_info(order.cancer_species)
#         item["specific"] = order.specific
#         item["age"] = order.age
#         item["send_user"] = await get_user_name(order.send_user_id)
#         if order.sex == 1:
#             item["sex_info"] = "男"
#         elif order.sex == 2:
#             item["sex_info"] = "女"
#         else:
#             item["sex_info"] = "未知"
#         item["interpret"] = await get_user_name(interpreting.interpret_id)
#         item["approve"] = await get_user_name(interpreting.approve_id)
#         item["approve_at"] = str(interpreting.approve_at)[:19] if interpreting.approve_at else ""
#         if interpreting.approve_status == 0:
#             item["approve_status_info"] = "待解读"
#         elif interpreting.approve_status == 1:
#             item["approve_status_info"] = "待审核"
#         elif interpreting.approve_status == 2:
#             item["approve_status_info"] = "已审核"
#         elif interpreting.approve_status == 3:
#             item["approve_status_info"] = "已拒绝"
#         else:
#             item["approve_status_info"] = "未知"
#         item["info6"] = convert_percentage(item["info6"])
#         item["info17"] = convert_percentage(item["info17"])
#         # item["info18"] = convert_percentage(item["info18"])
#         # item["info19"] = convert_percentage(item["info19"])
#         # if is_number(item["info6"]):
#         #     item["info6"] = f"{round(float(item['info6']) * 100, 2)}%"
#         # if "%" in item["info6"]:
#         #     item["info6"] = "{}%".format(round(float(str(item["info6"]).replace("%", "")), 2))
#     return res(data=dict(data=data, total=total))


@router.get("/down_batch_import_extract_excel_model", summary="下载提取结果批量导入模板")
async def down_batch_import_extract_excel_model():
    return FileResponse(path=os.path.join("file", "model", "提取结果批量导入.xlsx"), filename="提取结果批量导入.xlsx")


@router.get("/down_batch_import_library_excel_model", summary="下载建库结果批量导入模板")
async def down_batch_import_library_excel_model():
    print("下载数据")
    print(os.path.join("file", "model", "建库结果批量导入模板.xlsx"))
    return FileResponse(path=os.path.join("file", "model", "建库结果批量导入模板.xlsx"), filename="建库结果批量导入模板11.xlsx")


@router.get("/down_batch_import_capture_excel_model", summary="下载捕获结果批量导入模板")
async def down_batch_import_capture_excel_model():
    return FileResponse(path=os.path.join("file", "model", "捕获结果批量导入模板.xlsx"), filename="捕获结果批量导入模板.xlsx")


@router.get("/down_batch_import_outsource_excel_model", summary="下载外包数据批量导入模板")
async def down_batch_import_outsource_excel_model():
    return FileResponse(path=os.path.join("file", "model", "批量导入外包数据模板.xlsx"), filename="批量导入外包数据模板.xlsx")


@router.post("/batch_import_extract", summary="批量导入提取结果")
async def batch_import_extract(reuqest: Request, file: UploadFile = File(...)):
    uid, _ = await get_user_by_request(reuqest)
    content = await file.read()
    data = pd.read_excel(content)
    columns = data.columns.values.tolist()
    data_list = data.values.tolist()
    if columns != ["样本编号", "选择流程", "部门", "核酸浓度（ng/μL）", "回溶体积（μL）", "od260_280", "od260_230",
                   "核酸类型", "试剂盒", "试剂盒批次"]:
        raise HTTPException(status_code=500, detail="提交表格模板不对")
    insert_data = []
    for item in data_list:
        sample_no = item[0]
        sample = await InspectOrderSample.filter(sample_no=sample_no).first()
        if not sample:
            raise HTTPException(status_code=500, detail="样本编号错误")
        completion = await CompletionStatus.filter(completion_status=6, is_complete=27, sample_id=sample.id).first()
        if not completion:
            raise HTTPException(status_code=500, detail="样本实验流程不存在未完成任务")
        select_completion = await get_dataoption_data(item[1])
        if not select_completion or select_completion.id not in [6, 7, 8, 9]:
            raise HTTPException(status_code=500, detail="选择流程数据不正确！")
        department = await get_department_data(item[2])
        if not department:
            raise HTTPException(status_code=500, detail="部门数据错误！")
        if not item[3] or str(item[3]).replace(" ", "") == "" or str(item[3]) == "nan":
            raise HTTPException(status_code=500, detail="核酸浓度（ng/μL）数据不能为空！")
        if not item[4] or str(item[4]).replace(" ", "") == "" or str(item[4]) == "nan":
            raise HTTPException(status_code=500, detail="回溶体积（μL）数据不能为空！")
        if str(item[5]).replace(" ", "") == "" or str(item[5]) == "nan":
            raise HTTPException(status_code=500, detail="od260_280数据不能为空！")
        if str(item[6]).replace(" ", "") == "" or str(item[6]) == "nan":
            raise HTTPException(status_code=500, detail="od260_230数据不能为空！")
        if not item[7] or str(item[7]).replace(" ", "") == "" or str(item[7]) == "nan":
            raise HTTPException(status_code=500, detail="核酸类型数据不能为空！")
        reagent = await get_dataoption_data(item[8])
        if not reagent or reagent.id not in [71, 72, 73, 130, 131]:
            raise HTTPException(status_code=500, detail="试剂盒数据不正确！")
        if not item[9] or str(item[9]).replace(" ", "") == "" or str(item[9]) == "nan":
            raise HTTPException(status_code=500, detail="试剂盒批次数据不能为空！")
        insert_data.append([completion, select_completion, department, item[3], item[4], item[5], item[6], item[7],
                            reagent, item[9]])
    for item in insert_data:
        completion = item[0]
        d_data = dict(consistence=item[3], extraction_kit=item[8].name, extraction_kit_batch=item[9], nucleic_type=item[7],
                      od260_230=item[6], od260_280=item[5], volume=item[4], test_kit="")
        completion.is_complete = 28
        completion.txt_content = str(d_data)
        await completion.save()
        if item[1].id != 9:  # 不是外包
            obj = await CompletionStatus.create(completion_status=item[1].id,
                                                department_id=item[2].id, sample_id=completion.sample_id, is_complete=27)
            await InspectOrderSample.filter(pk=completion.sample_id).update(completion_id=obj.id)
    return res()


@router.post("/interpreting_bind", summary="解读数据绑定主单据")
async def interpreting_bind(request: Request, host_id: int = Body(...), follow_ids: List[int] = Body(...)):
    uid, _ = await get_user_by_request(request)
    for follow_id in follow_ids:
        if not await InterpretBind.filter(host_id=host_id, follow_id=follow_id).exists():
            await InterpretBind.create(host_id=host_id, follow_id=follow_id, user_id=uid)
        await SampleInterpreting.filter(sample_id=follow_id).update(approve_status=2, approve_at=datetime.datetime.now(),
                                                                    approve_desc="直接完成", approve_id=uid)
    return res()


@router.get("/get_interpreting_bind", summary="获取解读数据绑定")
async def get_interpreting_bind(sample_id: int, page: int = 1, limit: int = 10):
    query = InterpretBind.filter(Q(host_id=sample_id) | Q(follow_id=sample_id))
    total = await query.count()
    data = await query.offset((page - 1) * limit).limit(limit).values()
    for item in data:
        item["host_data"] = await get_sample_info(item["host_id"])
        item["follow_data"] = await get_sample_info(item["follow_id"])
    return res(data=dict(data=data, total=total))


@router.post("/batch_import_capture_excel_model", summary="批量导入捕获结果")
async def batch_import_capture_excel_model(reuqest: Request, file: UploadFile = File(...)):
    uid, _ = await get_user_by_request(reuqest)
    content = await file.read()
    data = pd.read_excel(content)
    columns = data.columns.values.tolist()
    data_list = data.values.tolist()
    if columns != ["样本编号", "选择流程", "部门", "文库投入体积（μL）", "捕获产物浓度（ng/μL)", "捕获产物体积（μL）", "试剂盒",
                   "试剂盒批次", "捕获探针", "探针批次"]:
        raise HTTPException(status_code=500, detail="提交表格模板不对")
    insert_data = []
    for item in data_list:
        sample_no = item[0]
        sample = await InspectOrderSample.filter(sample_no=sample_no).first()
        if not sample:
            raise HTTPException(status_code=500, detail="样本编号错误")
        completion = await CompletionStatus.filter(completion_status=8, is_complete=27, sample_id=sample.id).first()
        if not completion:
            raise HTTPException(status_code=500, detail="样本实验流程不存在未完成任务")
        select_completion = await get_dataoption_data(item[1])
        if not select_completion or select_completion.id not in [6, 7, 8, 9]:
            raise HTTPException(status_code=500, detail="选择流程数据不正确！")
        department = await get_department_data(item[2])
        if not department:
            raise HTTPException(status_code=500, detail="部门数据错误！")
        if not item[3] or str(item[3]).replace(" ", "") == "" or str(item[3]) == "nan":
            raise HTTPException(status_code=500, detail="文库投入体积（μL）数据不能为空！")
        if not item[4] or str(item[4]).replace(" ", "") == "" or str(item[4]) == "nan":
            raise HTTPException(status_code=500, detail="捕获产物浓度（ng/μL)数据不能为空！")
        if str(item[5]).replace(" ", "") == "" or str(item[5]) == "nan":
            raise HTTPException(status_code=500, detail="捕获产物体积（μL）数据不能为空！")
        if str(item[6]).replace(" ", "") == "" or str(item[6]) == "nan":
            raise HTTPException(status_code=500, detail="试剂盒数据不能为空！")
        reagent = await get_dataoption_data(item[6])
        if not reagent or reagent.id not in [77, 78]:
            raise HTTPException(status_code=500, detail="试剂盒数据不正确！")
        if not item[7] or str(item[7]).replace(" ", "") == "" or str(item[7]) == "nan":
            raise HTTPException(status_code=500, detail="试剂盒批次数据不能为空！")
        if str(item[8]).replace(" ", "") == "" or str(item[8]) == "nan":
            raise HTTPException(status_code=500, detail="捕获探针数据不能为空！")
        probe = await get_dataoption_data(item[8])
        if not probe or probe.id not in [79, 80, 81, 82]:
            raise HTTPException(status_code=500, detail="捕获探针据不正确！")
        if not item[9] or str(item[9]).replace(" ", "") == "" or str(item[9]) == "nan":
            raise HTTPException(status_code=500, detail="探针批次数据不能为空！")
        insert_data.append([completion, select_completion, department, item[3], item[4], item[5], item[6], item[7],
                            reagent.name, item[9]])
    for item in insert_data:
        completion = item[0]
        d_data = dict(library_consistence="", library_volume=item[3], capture_consistence=item[4], capture_volume=item[5],
                      capture_reagent=item[6], capture_reagent_batch=item[7], capture_probe=item[8],
                      capture_probe_batch=item[9])
        completion.is_complete = 28
        completion.txt_content = str(d_data)
        await completion.save()
        if item[1].id != 9:  # 不是外包
            obj = await CompletionStatus.create(completion_status=item[1].id,
                                                department_id=item[2].id, sample_id=completion.sample_id, is_complete=27)
            await InspectOrderSample.filter(pk=completion.sample_id).update(completion_id=obj.id)
    return res()


@router.post("/batch_import_library_excel_model", summary="批量导入建库结果")
async def batch_import_library_excel_model(reuqest: Request, file: UploadFile = File(...)):
    uid, _ = await get_user_by_request(reuqest)
    content = await file.read()
    data = pd.read_excel(content)
    columns = data.columns.values.tolist()
    data_list = data.values.tolist()
    if columns != ["样本编号", "选择流程", "部门", "核酸投入体积（μL）", "文库浓度（ng/μL)", "文库体积 （μL）", "试剂盒", "试剂盒批次"]:
        raise HTTPException(status_code=500, detail="提交表格模板不对")
    insert_data = []
    for item in data_list:
        sample_no = item[0]
        sample = await InspectOrderSample.filter(sample_no=sample_no).first()
        if not sample:
            raise HTTPException(status_code=500, detail="样本编号错误")
        completion = await CompletionStatus.filter(completion_status=7, is_complete=27, sample_id=sample.id).first()
        if not completion:
            raise HTTPException(status_code=500, detail="样本实验流程不存在未完成任务")
        select_completion = await get_dataoption_data(item[1])
        if not select_completion or select_completion.id not in [6, 7, 8, 9]:
            raise HTTPException(status_code=500, detail="选择流程数据不正确！")
        department = await get_department_data(item[2])
        if not department:
            raise HTTPException(status_code=500, detail="部门数据错误！")
        if not item[3] or str(item[3]).replace(" ", "") == "" or str(item[3]) == "nan":
            raise HTTPException(status_code=500, detail="核酸投入体积（μL）数据不能为空！")
        if not item[4] or str(item[4]).replace(" ", "") == "" or str(item[4]) == "nan":
            raise HTTPException(status_code=500, detail="文库浓度（ng/μL)数据不能为空！")
        if str(item[5]).replace(" ", "") == "" or str(item[5]) == "nan":
            raise HTTPException(status_code=500, detail="文库体积 （μL）数据不能为空！")
        if str(item[6]).replace(" ", "") == "" or str(item[6]) == "nan":
            raise HTTPException(status_code=500, detail="试剂盒数据不能为空！")
        reagent = await get_dataoption_data(item[6])
        if not reagent or reagent.id not in [74, 75, 76]:
            raise HTTPException(status_code=500, detail="试剂盒数据不正确！")
        if not item[7] or str(item[7]).replace(" ", "") == "" or str(item[7]) == "nan":
            raise HTTPException(status_code=500, detail="试剂盒批次数据不能为空！")
        insert_data.append([completion, select_completion, department, item[3], item[4], item[5], item[6], item[7]])
    for item in insert_data:
        completion = item[0]
        d_data = dict(nucleic_consistence="", nucleic_volume=item[3], library_consistence=item[4],
                      library_volume=item[5], library_reagent=item[6], library_reagent_batch=item[7])
        completion.is_complete = 28
        completion.txt_content = str(d_data)
        await completion.save()
        if item[1].id != 9:  # 不是外包
            obj = await CompletionStatus.create(completion_status=item[1].id,
                                                department_id=item[2].id, sample_id=completion.sample_id, is_complete=27)
            await InspectOrderSample.filter(pk=completion.sample_id).update(completion_id=obj.id)
    return res()


@router.post("/batch_import_outsource_excel_model", summary="外包数据批量导入")
async def batch_import_outsource_excel_model(reuqest: Request, file: UploadFile = File(...)):
    uid, _ = await get_user_by_request(reuqest)
    content = await file.read()
    data = pd.read_excel(content)
    columns = data.columns.values.tolist()
    data_list = data.values.tolist()
    if columns != ["样本编号", "选择流程", "部门", "是否直接完成", "外包商", "外包商类型", "外包商-产品", "外包商-平台", "外包商-芯片",
                   "快递公司", "快递编号", "外包开始时间", "外包结束时间"]:
        raise HTTPException(status_code=500, detail="提交表格模板不对")
    insert_data = []
    for item in data_list:
        sample_no = item[0]
        sample = await InspectOrderSample.filter(sample_no=sample_no).first()
        if not sample:
            raise HTTPException(status_code=500, detail="样本编号错误")
        completion = item[1]
        department = item[2]
        is_complete = item[3]
        outsourcer = item[4]
        outsourcer_type = item[5]
        product = item[6]
        platform = item[7]
        chip = item[8]
        express_company = item[9]
        express_size = item[10]
        start_time = item[11]
        end_time = item[12]
        if completion == "无" and is_complete == "否":
            raise HTTPException(status_code=500, detail="外包数据没有直接完成，下阶段流程选择错误")
        if department == "无" and is_complete == "否":
            raise HTTPException(status_code=500, detail="外包数据没有直接完成，下阶段部门选择错误")
        outsourcer_data = await OutsourcerInfo.filter(name=outsourcer).first()
        if not outsourcer_data:
            raise HTTPException(status_code=500, detail="外包商数据错误")
        outsourcer_type_data = await get_dataoption_data(outsourcer_type)
        if not outsourcer_type_data or outsourcer_type_data.id not in [31, 32, 33, 34]:
            raise HTTPException(status_code=500, detail="外包商类型数据错误")
        product_data = await OutsourcerProductInfo.filter(name=product).first()
        if not product_data:
            raise HTTPException(status_code=500, detail="外包商-产品数据错误")
        platform_data = await get_dataoption_data(platform)
        if not platform_data or platform_data.id not in [64, 65]:
            raise HTTPException(status_code=500, detail="外包商-平台数据错误")
        chip_data = await get_dataoption_data(chip)
        print(f"{chip_data=}, {chip=}")
        if not chip_data or chip_data.id not in [66, 67, 68, 69]:
            raise HTTPException(status_code=500, detail="外包商-芯片数据错误")
        express_company_data = await get_dataoption_data(express_company)
        if not express_company_data or express_company_data.id not in [20, 21, 22, 23, 24, 25, 26]:
            raise HTTPException(status_code=500, detail="快递公司数据错误")
        if not start_time:
            raise HTTPException(status_code=500, detail="外包开始时间数据错误")
        if not end_time:
            raise HTTPException(status_code=500, detail="外包结束时间数据错误")
        insert_data.append([sample, completion, department, is_complete, outsourcer_data, outsourcer_type_data,
                            product_data, platform_data, chip_data, express_company_data, express_size, start_time,
                            end_time])
    for item in insert_data:
        obj = await CompletionStatus.create(completion_status=9, is_complete=28, express_company=item[9].id,
                                            express_size=item[10], outsourcer_type=item[5].id, start_time=item[11],
                                            end_time=item[12], out_product=item[6].id, platform=item[7].id,
                                            chip=item[8].id, outsource_id=item[4].id, sample_id=item[0].id, uid=uid)
        if is_complete == "是":
            pass
        else:
            department = await Department.filter(name=item[2]).first()
            department_id = department.id if department else None
            completion = await get_dataoption_data(item[1])
            completion_id = completion.id if completion else None
            obj = await CompletionStatus.create(completion_status=completion_id, department_id=department_id,
                                                sample_id=item[0].id, is_complete=27)
            await InspectOrderSample.filter(pk=item[0].id).update(completion_id=obj.id)
    return res()


# @router.post("/down_interpreting_management_by_sample_no", summary="根据多个样本编号导出数据")
# async def down_interpreting_management_by_sample_no(sample_nos: str = Body(..., embed=True)):
#     sample_nos = sample_nos.split(",")
#     print(f"{sample_nos=}")
#     data = await InspectOrderSample.filter(sample_no__in=sample_nos).all()
#     columns = ["解读人员", "审核人", "审核状态", "审核时间", "是否加急", "备注", "异常备注", "报告截止日期", "销售人员", "产品名称",
#                "样本编号", "样本名称", "样本类型", "收样时间", "年龄", "性别", "平台", "芯片", "捕获探针", "患者癌种", "具体癌种",
#                "就诊医院", "就诊科室", "就诊医生", "门诊/住院号", "DNA总量(ng)", "预文库总量(ng)", "报告结果（阴/阳/无）", "外包商"]
#     excel_data = []
#     for item in data:
#         order = await InspectOrder.filter(pk=item.order_id).first()
#         interpret = await SampleInterpreting.filter(sample_id=item.id).first()
#         project = await ProjectInfo.filter(pk=item.project_id).first()
#         project_info = await get_prodcut_level(item.project_id, product_info=[])
#         if interpret:
#             interpret_user = await get_user_name(interpret.interpret_id) if interpret.interpret_id else ""
#             approve = await get_user_name(interpret.approve_id) if interpret.approve_id else ""
#             if interpret.approve_status == 0:
#                 approve_status_info = "待解读"
#             elif interpret.approve_status == 1:
#                 approve_status_info = "待审核"
#             elif interpret.approve_status == 2:
#                 approve_status_info = "已审核"
#             else:
#                 approve_status_info = "未知"
#             approve_at = str(interpret.approve_at)[:19] if interpret.approve_at else ""
#             info_1 = ""
#             result_info = eval(interpret.result) if interpret.result else []
#             if result_info:
#                 info_1 = result_info[0].get("info2", "")
#         else:
#             interpret_user = ""
#             approve = ""
#             approve_status_info = "待分配"
#             approve_at = ""
#             info_1 = ""
#         is_urgent = await get_dataoption_info(order.is_urgent)
#         sample_desc = item.sample_desc
#         abnormal_desc = item.abnormal_desc
#         deadline_dt = str(item.deadline_dt)[:10]
#         send_user = await get_user_name(order.send_user_id)
#         project_name = project.name
#         sample_no = item.sample_no
#         nickname = order.nickname
#         sample_type_info = await get_dataoption_info(item.sample_type)
#         gather_dt = str(item.gather_dt)[:10]
#         age = order.age
#         if order.sex == 1:
#             sex = "男"
#         else:
#             sex = "女"
#         cancer_species = await get_dataoption_info(order.cancer_species)
#         specific = order.specific
#         hospital = order.hospital
#         visiting_department = order.visiting_department
#         doctor = order.doctor
#         hospital_num = order.hospital_num
#         bioinformatics_data = await get_bioinformatics_data(item.id)
#         dna_total = bioinformatics_data.get("dna_total", "")
#         library_total = bioinformatics_data.get("library_total", "")
#         # 外包
#         outsource = await CompletionStatus.filter(sample_id=item.id, completion_status=9).order_by("-id").first()
#         outsource_probe = ""
#         if outsource:
#             outsource_info = await OutsourcerInfo.filter(id=outsource.outsource_id).first()
#             outsource_probe = outsource_info.name if outsource_info else ""
#         completion_data = await get_completion_status_info_tool(item.completion_id)
#         chip_info = completion_data[0].get("chip_info", "") if completion_data else ""
#         platform_info = completion_data[0].get("platform_info", "") if completion_data else ""
#         last_probe = await CompletionStatus.filter(sample_id=item.id, completion_status=8).order_by("-id").first()
#         capture_probe = ""
#         if last_probe:
#             if last_probe.txt_content:
#                 capture_probe = eval(last_probe.txt_content).get("capture_probe", "")
#         excel_data.append([interpret_user, approve, approve_status_info, approve_at, is_urgent, sample_desc,
#                            abnormal_desc, deadline_dt, send_user, project_info, sample_no, nickname, sample_type_info,
#                            gather_dt, age, sex, platform_info, chip_info, capture_probe, cancer_species, specific,
#                            hospital, visiting_department, doctor, hospital_num, dna_total, library_total, info_1,
#                            outsource_probe])
#     xlsx_file = io.BytesIO()
#     df = pd.DataFrame(excel_data, columns=columns)
#     df.to_excel(xlsx_file, index=False)
#     xlsx_file.seek(0)
#     filename = f"data.xlsx"
#     headers = {"Content-Disposition": f"attachment;filename={filename}"}
#     return StreamingResponse(xlsx_file, media_type="application/x-xls", headers=headers)


@router.post("/down_interpreting_management_by_sample_no", summary="生信根据多个样本编号导出数据")
async def down_interpreting_management_by_sample_no(sample_nos: str = Body(..., embed=True)):
    sample_nos = sample_nos.split(",")
    print(f"{sample_nos=}")
    data = await InspectOrderSample.filter(sample_no__in=sample_nos).all()
    columns = ["执行人员", "审核人", "审核状态", "审核备注", "是否加急", "样本编号", "样本名称", "产品名称", "报告截止日期", "平台",
               "芯片", "捕获探针", "核酸类型", "是否对照", "备注", "异常备注", "当前流程", "当前流程状态", "外包-产品", "样本类型",
               "样本属性", "审核时间", "结果"]
    excel_data = []
    for item in data:
        order = await InspectOrder.filter(pk=item.order_id).first()
        bioinformatic = await SampleBioInformatics.filter(sample_id=item.id).first()
        if bioinformatic:
            interpret_user = await get_user_name(bioinformatic.execute_id) if bioinformatic.execute_id else ""
            approve = await get_user_name(bioinformatic.approve_id) if bioinformatic.approve_id else ""
            if bioinformatic.approve_status == 0:
                approve_status_info = "待提交"
            elif bioinformatic.approve_status == 1:
                approve_status_info = "已审核"
            elif bioinformatic.approve_status == 2:
                approve_status_info = "已拒绝"
            elif bioinformatic.approve_status == 3:
                approve_status_info = "待审核"
            else:
                approve_status_info = "未知"
            approve_at = str(bioinformatic.approve_at)[:19] if bioinformatic.approve_at else ""
            approve_desc = bioinformatic.approve_desc if bioinformatic.approve_at else ""
            result = bioinformatic.result
        else:
            interpret_user = ""
            approve = ""
            approve_status_info = "待分配"
            approve_at = ""
            approve_desc = ""
            result = ""
        is_urgent = await get_dataoption_info(order.is_urgent)
        sample_desc = item.sample_desc
        abnormal_desc = item.abnormal_desc
        deadline_dt = str(item.deadline_dt)[:10]
        project_info = await get_prodcut_level(item.project_id, product_info=[])
        sample_no = item.sample_no
        nickname = order.nickname
        sample_type_info = await get_dataoption_info(item.sample_type)
        sample_attribute_info = await get_dataoption_info(item.sample_attribute)
        # 外包
        outsource = await CompletionStatus.filter(sample_id=item.id, completion_status=9).order_by("-id").first()
        outsource_probe = ""
        if outsource:
            outsource_info = await OutsourcerInfo.filter(id=outsource.outsource_id).first()
            outsource_probe = outsource_info.name if outsource_info else ""
        completion_data = await get_completion_status_info_tool(item.completion_id)
        chip_info = completion_data[0].get("chip_info", "") if completion_data else ""
        platform_info = completion_data[0].get("platform_info", "") if completion_data else ""
        completion_status_info = completion_data[0].get("completion_status_info", "") if completion_data else ""
        is_complete_info = completion_data[0].get("is_complete_info", "") if completion_data else ""
        out_product_info = completion_data[0].get("out_product_info", "") if completion_data else ""
        last_probe = await CompletionStatus.filter(sample_id=item.id, completion_status=8).order_by("-id").first()
        capture_probe = ""
        if last_probe:
            if last_probe.txt_content:
                capture_probe = eval(last_probe.txt_content).get("capture_probe", "")
        last_data = await CompletionStatus.filter(sample_id=item.id, completion_status=6).order_by("-id").first()
        nucleic_type = ""
        if last_data:
            if last_data.txt_content:
                nucleic_type = eval(last_data.txt_content).get("nucleic_type")
        is_compare_info = await get_dataoption_info(item.is_compare)
        excel_data.append([interpret_user, approve, approve_status_info, approve_desc, is_urgent, sample_no, nickname,
                           project_info, deadline_dt, platform_info, chip_info, capture_probe, nucleic_type,
                           is_compare_info, sample_desc, abnormal_desc, completion_status_info, is_complete_info,
                           out_product_info, sample_type_info, sample_attribute_info, approve_at, result])
    print(excel_data)
    print(columns)
    df = pd.DataFrame(excel_data, columns=columns)
    file_path = os.path.join("down_files", f"data_{str(datetime.datetime.now())[:19]}.xlsx")
    print(file_path)
    df.to_excel(file_path, sheet_name='Sheet1', index=False)
    return FileResponse(path=file_path, media_type="application/x-xls")

    # print(f"{excel_data=}")
    # xlsx_file = io.BytesIO()
    # df = pd.DataFrame(excel_data, columns=columns)
    # df.to_excel(xlsx_file, index=False)
    # xlsx_file.seek(0)
    # filename = f"data.xlsx"
    # headers = {"Content-Disposition": f"attachment;filename={filename}"}
    # print(f"{headers=}")
    # return StreamingResponse(xlsx_file, media_type="application/x-xls", headers=headers)


@router.get("/add_interpret_databaase_data", summary="手动增加解读数据库的数据")
async def add_interpret_databaase_data(interpret_id: int):
    interpret = await SampleInterpreting.filter(pk=interpret_id).first()
    if not interpret.result:
        raise HTTPException(status_code=500, detail="该数据暂无解读结果数据")
    interpret_data = eval(str(interpret.result).replace(":null", ':""').replace(":nan", ':""')) if interpret.result else []
    sample = await InspectOrderSample.filter(pk=interpret.sample_id).first()
    if await InterpretingDataBase.filter(interpreting_id=interpret.id).exists():
        await InterpretingDataBase.filter(interpreting_id=interpret.id).delete()
    for item in interpret_data:
        item_data = {k: v for k, v in item.items() if str(k).startswith("info")}
        item_data["interpreting_id"] = interpret.id
        item_data["order_id"] = sample.order_id
        item_data["sample_id"] = interpret.sample_id
        await InterpretingDataBase.create(**item_data)
    return res()
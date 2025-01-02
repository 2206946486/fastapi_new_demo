#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Time    : 2023/7/7 8:38
# @Author  : LJ
# @File    : base_handler.py
import os
import io
import re
import datetime
import copy

from fastapi import APIRouter, Body, Form, UploadFile, File, Request
from typing import List
from tortoise.queryset import Q
from fastapi.responses import StreamingResponse, FileResponse

from apps.tools import res, State, formatting_time, pwd_context, get_user_by_request, get_user_name, get_dataoption_info
from apps.models import Datatype, Dataoption, Department, User, Menu, Role, MenuFuncApis, RoleFunc, DownloadFilsTask
from apps.tools import MENU

router = APIRouter()


@router.get("/get_data_type_option", summary="获取所有下拉框数据")
async def get_data_type_option():
    query = await Datatype.filter().all().values()
    for item in query:
        option = await Dataoption.filter(search_id=item["id"]).all().values()
        item["option"] = option
    return res(data=query)


@router.get("/get_data_option", summary="获取指定下拉框数据")
async def get_data_option(search: str):
    search = await Datatype.filter(search=search).first()
    assert search, State.PARAMS_ERROR
    option = await Dataoption.filter(search_id=search.id).filter(~Q(id=45)).all().values()
    return res(data=option)


@router.post("/add_data_type", summary="增加下拉框数据类型")
async def add_data_type(name: str = Body(...), search: str = Body(...), desc: str = Body(None)):
    assert not await Datatype.filter(search=search).exists(), State.DATA_EXISTENCE
    await Datatype.create(name=name, search=search, desc=desc)
    return res()


@router.post("/add_data_option", summary="增加下拉框数据选项")
async def add_data_option(name: str = Body(...), search_id: int = Body(...), desc: str = Body(None)):
    assert not await Dataoption.filter(search_id=search_id, name=name).exists(), State.DATA_EXISTENCE
    await Dataoption.create(name=name, search_id=search_id, desc=desc)
    return res()


@router.delete("/delete_data_type", summary="删除下拉框数据类型")
async def delete_data_type(ids: List[int] = Body(..., embed=True)):
    query = await Datatype.filter(id__in=ids).all()
    for item in query:
        await Dataoption.filter(search_id=item.id).delete()
        await item.delete()
    return res()


@router.delete("/delete_data_option", summary="删除下拉框数据选项")
async def delete_data_option(ids: List[int] = Body(..., embed=True)):
    await Dataoption.filter(id__in=ids).delete()
    return res()


@router.put("/update_data_type", summary="修改下拉框数据类型")
async def update_data_type(id: int = Body(...), name: str = Body(...), desc: str = Body(...)):
    await Datatype.filter(id=id).update(name=name, desc=desc)
    return res()


@router.put("/update_data_option", summary="修改下拉框数据选项")
async def update_data_option(id: int = Body(...), name: str = Body(...), desc: str = Body("")):
    await Dataoption.filter(id=id).update(name=name, desc=desc)
    return res()


@router.get("/get_department", summary="获取所有部门信息")
async def get_department():
    query = Department.filter(is_delete=0)
    data = await query.values()
    total = await query.count()
    return res(data=dict(data=data, total=total))


@router.get("/get_department_by_option", summary="获取部门下拉列表")
async def get_department_by_option(is_pid: bool = False):
    """
    :param is_pid: True: 只查询父节点部门，False:查询所有部门
    :return:
    """
    if is_pid:
        query = await Department.filter(is_delete=0, pid=0).values("id", "name")
    else:
        query = await Department.filter(is_delete=0).values("id", "name")
    return res(data=query)


@router.post("/add_department", summary="新增部门")
async def add_department(request: Request, pid: int = Body(0), name: str = Body(...), desc: str = Body(None)):
    assert not await Department.filter(name=name, pid=pid).exists(), State.DATA_EXISTENCE
    obj = await Department.create(pid=pid, name=name, desc=desc)
    return res()


@router.put("/update_department", summary="修改部门")
async def update_department(request: Request, id: int = Body(...), name: str = Body(...), desc: str = Body(...),
                            pid: int = Body(0)):
    assert not await Department.filter(name=name, id__not_in=[id]).exists(), State.DATA_EXISTENCE
    await Department.filter(id=id).update(name=name, desc=desc, pid=pid)
    return res()


@router.delete("/delete_department", summary="删除部门")
async def delete_department(request: Request, id: int = Body(..., embed=True)):
    """
    :param id: 部门id
    :return:
    """
    ids = await Department.filter(is_delete=0).filter(Q(id=id) | Q(pid=id)).all()
    assert not await User.filter(department_id__in=[item.id for item in ids]).exists(), \
        State.DEPARTMENT_EXISTENCE_USER
    await Department.filter(Q(id=id) | Q(pid=id)).delete()
    return res()


@router.get("/get_all_user", summary="获取所有人员信息")
async def get_all_user(search: str = "", page: int = 1, limit: int = 10):
    query = User.filter(Q(job__icontains=search) | Q(nickname__icontains=search) | Q(phone__icontains=search) |
                        Q(mailbox__icontains=search))
    data = await query.order_by('-id').offset((page - 1) * limit).limit(limit).values()
    total = await query.count()
    data = formatting_time(data, args=["created_at", "updated_at", "entry_time"], is_type=2)
    for item in data:
        item.pop("password")
        item["department"] = ""
        if item["department_id"]:
            department = await Department.filter(pk=item["department_id"]).first()
            item["department"] = department.name
        item["role"] = ""
        if item["role_id"]:
            role = await Role.filter(pk=item["role_id"]).first()
            item["role"] = role.name
        item["region_info"] = await get_dataoption_info(item["region"])
    return res(data=dict(total=total, data=data))


@router.get("/get_user_by_option", summary="获取人员下拉框")
async def get_user_by_option(department_id: int = None, search: str = None):
    query = User.filter(is_delete=0)
    if department_id:
        query = query.filter(department_id=department_id)
    if search:
        query = query.filter(Q(nickname__icontains=search) | Q(username__icontains=search))
    data = await query.values("id", "nickname")
    return res(data=data)


@router.post("/add_user", summary="增加用户")
async def add_user(request: Request, username: str = Form(...), nickname: str = Form(...), phone: str = Form(...),
                   mailbox: str = Form(...), job: str = Form(...), pic: UploadFile = File(None),
                   entry_time: str = Form(...), region: str = Form(None), is_super: int = Form(0),
                   department_id: int = Form(...), role_id: int = Form(None)):
    assert await Department.filter(pk=department_id).exists(), State.DEPARTMENT_INVALID
    assert re.search(r'^[a-zA-Z][a-zA-Z0-9_]{2,15}$', username), State.USERNAME_INVALID
    assert re.search(r'^(1[3|4|5|6|7|8|9][0-9])\d{8}$', phone), State.PHONE_INVALID
    assert re.search(r"^\w+([-+.]\w+)*@\w+([-.]\w+)*\.\w+([-.]\w+)*$", mailbox), State.EMAIL_INVALID
    assert not await User.filter(
        Q(username=username) | Q(phone=phone) | Q(mailbox=mailbox)).exists(), State.DATA_EXISTENCE
    # e10adc3949ba59abbe56e057f20f883e >> 123456
    password = pwd_context.hash("e10adc3949ba59abbe56e057f20f883e")
    pic_path = f"pics/default.png"
    if pic:
        content = await pic.read()
        pic_path = f"pics/{username}.png"
        with open(pic_path, 'wb') as f:
            f.write(content)
    obj = await User.create(username=username, password=password, nickname=nickname, mailbox=mailbox, phone=phone,
                            job=job,
                            pic=pic_path, entry_time=entry_time, region=region, is_super=is_super,
                            department_id=department_id, role_id=role_id)
    return res()


@router.put("/update_user_info", summary="修改用户信息")
async def update_user_info(request: Request, id: int = Form(...), nickname: str = Form(None), phone: str = Form(None),
                           mailbox: str = Form(None), job: str = Form(None), pic: UploadFile = File(None),
                           entry_time: str = Form(None), region: str = Form(None), is_super: int = Form(None),
                           department_id: int = Form(None), role_id: int = Form(None), username: str = Form(None)
                           ):
    user = await User.filter(pk=id).first()
    if department_id:
        assert await Department.filter(pk=department_id).exists(), State.DEPARTMENT_INVALID
        user.department_id = department_id
    if phone:
        assert re.search(r'^(1[3|4|5|6|7|8|9][0-9])\d{8}$', phone), State.PHONE_INVALID
        assert not await User.filter(~Q(pk=id)).filter(phone=phone).exists(), State.DATA_EXISTENCE
        user.phone = phone
    if mailbox:
        assert not await User.filter(~Q(pk=id)).filter(mailbox=mailbox).exists(), State.DATA_EXISTENCE
        assert re.search(r"^\w+([-+.]\w+)*@\w+([-.]\w+)*\.\w+([-.]\w+)*$", mailbox), State.EMAIL_INVALID
        user.mailbox = mailbox
    if job:
        user.job = job
    if entry_time:
        user.entry_time = entry_time
    if region:
        user.region = region
    if is_super is not None:
        user.is_super = is_super
    if pic:
        content = await pic.read()
        pic_path = user.pic
        os.remove(pic_path)
        with open(pic_path, 'wb') as f:
            f.write(content)
    if nickname:
        user.nickname = nickname
    if role_id:
        user.role_id = role_id
    if username:
        user.username = username
    await user.save()
    return res()


@router.delete("/delete_user", summary="删除用户")
async def delete_user(request: Request, ids: List[int] = Body(...), status: bool = Body(False)):
    """
    :param ids:
    :param status: 状态： True: 禁用， False:启用
    :return:
    """
    await User.filter(pk__in=ids).update(is_delete=status)
    data = await User.filter(pk__in=ids).all()
    for item in data:
        item.is_delete = status
        await item.save()
    return res()


@router.get("/get_all_menu", summary="获取所有的目录")
async def get_all_menu(search: str = ""):
    data = await Menu.filter(name__icontains=search).filter(pid=0).values("id", "name", "is_delete", "path")
    for item in data:
        item["children"] = await Menu.filter(pid=item["id"]).values("id", "name", "is_delete", "path")
    return res(data=data)


@router.get("/get_menu_by_pid", summary="根据父节点查询页面")
async def get_menu_by_pid(pid: int = 0):
    query = await Menu.filter(pid=pid, is_delete=0).values("id", "name")
    return res(data=query)


@router.post("/add_menu", summary="新增页面")
async def add_menu(pid: int = Body(0), name: str = Body(...), path: str = Body(...)):
    assert not await Menu.filter(Q(name=name) | Q(path=path)), State.DATA_EXISTENCE
    await Menu.create(pid=pid, name=name, path=path)
    return res()


@router.put("/update_menu", summary="修改页面")
async def update_menu(id: int = Body(...), pid: int = Body(...), name: str = Body(...), path: str = Body(""),
                      is_delete: int = Body(0)):
    assert not await Menu.filter(~Q(pk=id)).filter(Q(name=name) | Q(path=path)), State.DATA_EXISTENCE
    await Menu.filter(pk=id).update(pid=pid, name=name, path=path, is_delete=is_delete,
                                    updated_at=datetime.datetime.now())
    return res()


@router.delete("/delete_menu", summary="禁用页面")
async def delete_menu(ids: List[int] = Body(...), status: bool = Body(False)):
    """
    禁用页面，如果是父节点，则会禁用父节点下的所有页面，如需启用，许手动修改子页面信息的启动状态
    :param ids:
    :param status: True:开始禁用， Flase:关闭禁用
    :return:
    """
    query = await Menu.filter(pk__in=ids).all()
    is_delete = 1 if status else 0
    for item in query:
        if item.pid == 0:
            await Menu.filter(pid=item.id).update(is_delete=is_delete)
        item.is_delete = is_delete
        await item.save()
    return res()


@router.get("/get_menu_apis", summary="获取页面下面绑定的功能")
async def get_menu_apis(menu_id: int):
    data = await MenuFuncApis.filter(menu_id=menu_id).values()
    return res(data=data)


@router.post("/add_menu_apis", summary="页面增加功能")
async def add_menu_apis(menu_id: int = Body(...), name: str = Body(...), title: str = Body(...)):
    assert not await MenuFuncApis.filter(menu_id=menu_id, name=name).exists(), State.DATA_EXISTENCE
    await MenuFuncApis.create(name=name, menu_id=menu_id, title=title)
    return res()


@router.delete("/delete_menu_apis", summary="删除页面功能")
async def delete_menu_apis(ids: List[int] = Body(..., embed=True)):
    await MenuFuncApis.filter(pk__in=ids).delete()
    await RoleFunc.filter(func_id__in=ids).delete()
    return res()


@router.get("/get_all_role", summary="获取所有角色列表")
async def get_all_role(search: str = "", page: int = 1, limit: int = 10):
    query = Role.filter(name__icontains=search)
    data = await query.offset((page - 1) * limit).limit(limit).values()
    total = await query.count()
    data = formatting_time(data)
    return res(data=dict(data=data, total=total))


@router.get("/get_all_role_list", summary="获取所有角色列表下拉框")
async def get_all_role_list():
    data = await Role.filter(is_delete=0).values("id", "name")
    return res(data=data)


@router.get("/get_func_by_role", summary="根据角色id所有模块功能")
async def get_func_by_role(role_id: int = None):
    menus = await Menu.filter(is_delete=0).all().values("id", "pid", "name")
    data = []
    for item in menus:
        data.append(item)
        funcs = await MenuFuncApis.filter(menu_id=item["id"]).values("id", "name", "menu_id")
        for f_item in funcs:
            data.append(dict(func_id=f_item["id"], name=f_item["name"], pid=f_item["menu_id"], id=10000 + f_item["id"]))
    choice_id = []
    for item in data:
        item["pid"] = None if item["pid"] == 0 else item["pid"]
    if role_id:
        is_choices = await RoleFunc.filter(role_id=role_id).all()
        choice_id = [10000 + item.func_id for item in is_choices if item.func_id]

    return res(data=dict(data=data, choice_id=choice_id))


@router.post("/add_role", summary="增加角色")
async def add_role(request: Request, name: str = Body(...), func_ids: List[int] = Body([])):
    assert not await Role.filter(name=name).exists(), State.DATA_EXISTENCE
    obj = await Role.create(name=name)
    for item in func_ids:
        await RoleFunc.create(role_id=obj.id, func_id=item)
    return res()


@router.put("/update_role", summary="修改角色")
async def update_role(request: Request, id: int = Body(...), name: str = Body(None), func_ids: List[int] = Body([])):
    if name:
        assert not await Role.filter(name=name).filter(~Q(id=id)).exists(), State.DATA_EXISTENCE
        await Role.filter(pk=id).update(name=name)
    # 已有权限
    hava_func = await RoleFunc.filter(role_id=id).all()
    hava_func = [item.func_id for item in hava_func]
    delete_func = set(hava_func) - set(func_ids)
    add_func = set(func_ids) - set(hava_func)
    await RoleFunc.filter(role_id=id, func_id__in=list(delete_func)).delete()
    for item in add_func:
        await RoleFunc.create(role_id=id, func_id=item)
    return res()


@router.delete("/delete_role", summary="删除角色")
async def delete_role(request: Request, ids: List[int] = Body(..., embed=True)):
    roles = await Role.filter(id__in=ids).all()
    for item in roles:
        await RoleFunc.filter(role_id=item.id).delete()
        await item.delete()
    return res()


@router.get("/get_page_permissions", summary="获取登录账号指定页面权限")
async def get_page_permissions(request: Request, path: str):
    """
    :param request:
    :param path: 目录下页面的 path
    :return:
    """
    page = await Menu.filter(path=path).first()
    assert page, State.PARAMS_ERROR
    page_func = await MenuFuncApis.filter(menu_id=page.pk).all()
    page_func_ids = [item.pk for item in page_func]
    uid, is_super = await get_user_by_request(request)
    user = await User.filter(pk=uid).first()
    if is_super:
        func_ids = page_func_ids
    else:
        user_funcs = await RoleFunc.filter(role_id=user.role_id).all()
        func_ids = [item.func_id for item in user_funcs]
    hava_func = set(page_func_ids) & set(func_ids)
    funcs = await MenuFuncApis.filter(menu_id=page.id).all().values("id", "name", "title")
    # print(f"{funcs=}")
    for item in funcs:
        item["is_show"] = True if item["id"] in hava_func else False
    data = dict()
    for item in funcs:
        data.update({item.get("title"): item.get("is_show")})
    # print(f"{data=}")
    return res(data=data)


@router.get("/menu", summary="菜单栏")
async def menu(request: Request):
    uid, is_super = await get_user_by_request(request)
    menus_copy = copy.deepcopy(MENU)
    if is_super:
        pass
    else:
        user = await User.filter(pk=uid).first()
        func = await RoleFunc.filter(role_id=user.role_id).all()
        menu_funcs = await MenuFuncApis.filter(pk__in=[item.func_id for item in func]).all()
        menu_list = await Menu.filter(pk__in=[item.menu_id for item in menu_funcs]).all()
        menus_data = [item.path for item in menu_list]
        for item in menus_copy:
            for i in range(len(item["children"]) - 1, -1, -1):
                if item["children"][i]["path"] not in menus_data:
                    item["children"].pop(i)
    data = [item for item in menus_copy if item["children"]]
    return res(data=data)


@router.get("/get_user_down_files", summary="获取下载文件任务列表")
async def get_user_down_files(request: Request, search: str = "", page: int = 1, limit: int = 10):
    uid, is_super = await get_user_by_request(request)
    query = DownloadFilsTask.filter(name__icontains=search)
    if not is_super:
        query = query.filter(user_id=uid)
    total = await query.count()
    data = await query.order_by("-id").offset((page - 1) * limit).limit(limit).values()
    for item in data:
        item["created_at"] = str(item["created_at"])[:19]
        item["user_info"] = await get_user_name(item["user_id"])
        if item["status"] == 0:
            item["status_info"] = "正在生成文件"
        elif item["status"] == 1:
            item["status_info"] = "成功"
        else:
            item["status_info"] = "失败"
    return res(data=dict(data=data, total=total))


@router.get("/user_down_file", summary="用户下载文件")
async def user_down_file(file_id: int):
    file = await DownloadFilsTask.filter(pk=file_id).first()
    assert file, State.DATA_NOT_EXISTENCE
    return FileResponse(path=file.file_path, filename=file.name)


@router.get("/user_down_data", summary="用户根据时间段下载数据")
async def user_down_data(request: Request, starttime: str, endtime: str):
    uid, is_super = await get_user_by_request(request)
    # print(request.scope)
    homepage = request.headers.get("homepage", None)
    assert homepage, State.PARAMS_ERROR
    homepage_data = await Menu.filter(path=homepage).first()
    assert homepage_data, State.PARAMS_ERROR
    name = homepage_data.name + starttime + "-" + endtime + ".xlsx"
    starttime += " 00:00:00"
    endtime += " 23:59:59"
    parameter = request.url.query
    await DownloadFilsTask.create(name=name, module_name=homepage_data.name, module_path=homepage, start_time=starttime,
                                  end_time=endtime, user_id=uid, parameter=parameter, created_at=datetime.datetime.now())
    return res()


@router.post("/user_down_data_by_ids", summary="用户根据数据id下载数据")
async def user_down_data(request: Request, data_ids: List[int] = Body(..., embed=True)):
    uid, is_super = await get_user_by_request(request)
    homepage = request.headers.get("homepage", None)
    assert homepage, State.PARAMS_ERROR
    homepage_data = await Menu.filter(path=homepage).first()
    assert homepage_data, State.PARAMS_ERROR
    name = homepage_data.name + str(datetime.datetime.now())[:19] + ".xlsx"
    await DownloadFilsTask.create(name=name, module_name=homepage_data.name, module_path=homepage, user_id=uid,
                                  parameter=str(data_ids), created_at=datetime.datetime.now())
    return res()
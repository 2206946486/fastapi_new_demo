#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Time    : 2024/5/14 15:36
# @Author  : LJ
# @File    : tasks.py
from celery import Celery


celery_app = Celery("worker",
                    broker="redis://:FrasergenMv7SA1OYXO@192.168.2.186:6380/2",
                    backend="redis://:FrasergenMv7SA1OYXO@192.168.2.186:6380/2",
                    include=["apps.tools.my_celery.__init__"]
)

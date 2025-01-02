FROM python:3.8.6
MAINTAINER LJ
ENV FASTAPP=Online
ENV TZ Asia/Shanghai
ADD ./LIMS /data/LIMS
WORKDIR /data/LIMS
RUN pip install -r requirements.txt
RUN ln -fs /usr/share/zoneinfo/${TZ} /etc/localtime \
    && echo ${TZ} > /etc/timezone
CMD ["python", "/data/LIMS/main.py"]
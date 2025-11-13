ARG BUILD_FROM=ghcr.io/hassio-addons/base-python:13.2.1
FROM ${BUILD_FROM}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

# 필요한 추가 패키지만 설치
# base-python 이미지 안에 이미 python3 는 들어있지만,
# 필요하다면 py3-pip 만 별도로 설치해도 됨.
RUN apk add --no-cache \
    git \
    py3-pip \
 && ln -sf /usr/bin/pip3 /usr/bin/pip || true

WORKDIR /opt/bot

# 애드온 파일 복사
COPY rootfs /

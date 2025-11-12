ARG BUILD_FROM=ghcr.io/hassio-addons/base-python:13.2.1
FROM ${BUILD_FROM}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

RUN apk add --no-cache \
    git \
    py3-pip

WORKDIR /opt/bot

COPY rootfs / 


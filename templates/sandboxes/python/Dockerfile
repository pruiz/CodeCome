# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: MIT

# CodeCome Python sandbox baseline.
# Marker convention: see README.md for VARNAME tokens.

FROM python:__PYTHON_VERSION__-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_INPUT=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    bash \
    ca-certificates \
    curl \
    file \
    git \
    jq \
    make \
    ripgrep \
    strace \
    unzip \
    wget \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip pipx virtualenv

WORKDIR /workspace

EXPOSE __APP_PORT__

CMD ["/bin/bash"]

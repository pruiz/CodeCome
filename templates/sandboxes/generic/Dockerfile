# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: MIT

# CodeCome generic sandbox baseline.
# Marker convention: see README.md for VARNAME tokens.

FROM debian:__DEBIAN_BASE_TAG__

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    bash \
    ca-certificates \
    curl \
    file \
    git \
    jq \
    make \
    python3 \
    python3-pip \
    ripgrep \
    strace \
    unzip \
    wget \
    xxd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

CMD ["/bin/bash"]

# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: MIT

# CodeCome Erlang / OTP sandbox baseline.
# Marker convention: see README.md for VARNAME tokens.

FROM erlang:__ERLANG_OTP_TAG__-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    MIX_ENV=test

RUN apt-get update && apt-get install -y \
    bash \
    ca-certificates \
    curl \
    file \
    gawk \
    git \
    jq \
    make \
    python3 \
    rebar3 \
    ripgrep \
    strace \
    unzip \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

EXPOSE __APP_PORT__
EXPOSE __MANAGEMENT_PORT__

CMD ["/bin/bash"]

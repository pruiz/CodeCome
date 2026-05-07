# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: MIT

# CodeCome Rust sandbox baseline.
# Marker convention: see README.md for VARNAME tokens.

FROM rust:__RUST_TOOLCHAIN_TAG__-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    CARGO_TERM_COLOR=always

RUN apt-get update && apt-get install -y \
    bash \
    ca-certificates \
    curl \
    file \
    git \
    jq \
    lldb \
    make \
    pkg-config \
    python3 \
    ripgrep \
    strace \
    unzip \
    wget \
    && rm -rf /var/lib/apt/lists/*

RUN rustup component add clippy rustfmt

WORKDIR /workspace

EXPOSE __APP_PORT__

CMD ["/bin/bash"]

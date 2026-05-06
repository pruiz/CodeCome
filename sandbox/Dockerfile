FROM debian:bookworm

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    bash \
    build-essential \
    ca-certificates \
    clang \
    clang-tools \
    cmake \
    curl \
    file \
    g++ \
    gcc \
    gdb \
    git \
    jq \
    lldb \
    make \
    ninja-build \
    pkg-config \
    python3 \
    python3-pip \
    ripgrep \
    strace \
    unzip \
    valgrind \
    wget \
    xxd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

CMD ["/bin/bash"]

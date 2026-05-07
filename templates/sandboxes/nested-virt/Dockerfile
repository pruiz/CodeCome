# CodeCome nested QEMU sandbox.
# Marker convention: see README.md for VARNAME tokens.
#
# Use only when the target genuinely needs nested virtualization
# (firmware, kernel, binary-only blobs, foreign architecture).

FROM debian:bookworm

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    bash \
    binutils \
    binutils-arm-none-eabi \
    binutils-aarch64-linux-gnu \
    bsdmainutils \
    ca-certificates \
    cpio \
    curl \
    file \
    gdb \
    gdb-multiarch \
    git \
    jq \
    make \
    python3 \
    python3-pip \
    qemu-system-arm \
    qemu-system-aarch64 \
    qemu-system-misc \
    qemu-system-x86 \
    qemu-utils \
    qemu-user-static \
    ripgrep \
    strace \
    unzip \
    wget \
    xxd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

CMD ["/bin/bash"]

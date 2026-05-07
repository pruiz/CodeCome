# CodeCome generic sandbox baseline.
# Marker convention: __VARNAME__ tokens are replaced by the bootstrap
# CLI (--var KEY=VAL) or by the agent during Phase 1b.

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

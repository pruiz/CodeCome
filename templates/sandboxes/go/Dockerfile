# CodeCome Go sandbox baseline.
# Marker convention: __VARNAME__ tokens.

FROM golang:__GO_VERSION__-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    GOFLAGS="-mod=readonly" \
    CGO_ENABLED=1

RUN apt-get update && apt-get install -y \
    bash \
    ca-certificates \
    curl \
    file \
    git \
    jq \
    make \
    python3 \
    ripgrep \
    strace \
    unzip \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

EXPOSE __APP_PORT__

CMD ["/bin/bash"]

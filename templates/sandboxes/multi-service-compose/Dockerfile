# CodeCome multi-service compose tooling image.
# This image is the *tooling* container for the multi-service stack.
# Real service images (app, db, cache, ...) belong in compose.

FROM debian:bookworm

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    bash \
    ca-certificates \
    curl \
    file \
    git \
    iputils-ping \
    jq \
    make \
    netcat-openbsd \
    python3 \
    python3-pip \
    ripgrep \
    strace \
    unzip \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

CMD ["/bin/bash"]

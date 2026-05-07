# CodeCome Node.js sandbox baseline.
# Marker convention: see README.md for VARNAME tokens.

FROM node:__NODE_VERSION__-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    NPM_CONFIG_UPDATE_NOTIFIER=false \
    npm_config_yes=true

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
    && rm -rf /var/lib/apt/lists/*

RUN corepack enable \
    && corepack prepare yarn@stable --activate \
    && corepack prepare pnpm@latest --activate

WORKDIR /workspace

EXPOSE __APP_PORT__

CMD ["/bin/bash"]

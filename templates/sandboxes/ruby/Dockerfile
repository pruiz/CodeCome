# CodeCome Ruby sandbox baseline.
# Marker convention: see README.md for VARNAME tokens.

FROM ruby:__RUBY_VERSION__-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    BUNDLE_PATH=/usr/local/bundle \
    BUNDLE_DISABLE_VERSION_CHECK=1

RUN apt-get update && apt-get install -y \
    bash \
    build-essential \
    ca-certificates \
    curl \
    file \
    git \
    jq \
    libssl-dev \
    libyaml-dev \
    make \
    python3 \
    ripgrep \
    strace \
    unzip \
    wget \
    && rm -rf /var/lib/apt/lists/*

RUN gem install bundler:2.5.13 rake

WORKDIR /workspace

EXPOSE __APP_PORT__

CMD ["/bin/bash"]

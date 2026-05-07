# CodeCome PHP sandbox baseline.
# Marker convention: __VARNAME__ tokens.

FROM php:__PHP_VERSION__-cli-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    COMPOSER_ALLOW_SUPERUSER=1 \
    COMPOSER_NO_INTERACTION=1

RUN apt-get update && apt-get install -y \
    bash \
    ca-certificates \
    curl \
    file \
    git \
    jq \
    libonig-dev \
    libxml2-dev \
    libzip-dev \
    make \
    python3 \
    ripgrep \
    strace \
    unzip \
    wget \
    zip \
    && rm -rf /var/lib/apt/lists/*

RUN docker-php-ext-install mbstring zip xml \
    && curl -fsSL https://getcomposer.org/installer | php -- \
       --install-dir=/usr/local/bin --filename=composer

WORKDIR /workspace

EXPOSE __APP_PORT__

CMD ["/bin/bash"]

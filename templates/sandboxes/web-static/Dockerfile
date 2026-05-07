# CodeCome static-web sandbox baseline.
# Marker convention: __VARNAME__ tokens.

FROM nginx:1.27-bookworm

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    bash \
    ca-certificates \
    curl \
    file \
    git \
    jq \
    ripgrep \
    strace \
    unzip \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Replace the default nginx config with one serving /workspace/src.
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf.template /etc/nginx/conf.d/default.conf.template

# The compose entrypoint will substitute __APP_PORT__ before nginx starts.
CMD ["/bin/bash", "-lc", "envsubst '$APP_PORT' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]

EXPOSE __APP_PORT__

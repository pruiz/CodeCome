# CodeCome .NET sandbox baseline.
# Marker convention: see README.md for VARNAME tokens.

FROM mcr.microsoft.com/dotnet/sdk:__DOTNET_SDK_TAG__

ENV DEBIAN_FRONTEND=noninteractive \
    DOTNET_CLI_TELEMETRY_OPTOUT=1 \
    DOTNET_NOLOGO=1 \
    DOTNET_GENERATE_ASPNET_CERTIFICATE=false

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

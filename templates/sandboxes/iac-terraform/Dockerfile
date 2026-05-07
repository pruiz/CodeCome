# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: MIT

# CodeCome Terraform IaC review sandbox.
# Marker convention: see README.md for VARNAME tokens.

FROM hashicorp/terraform:__TERRAFORM_VERSION__

ENV TF_IN_AUTOMATION=1 \
    TF_INPUT=0

# The hashicorp image is alpine-based.
RUN apk add --no-cache \
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
    wget

# Install tflint via the official installer.
RUN curl -fsSL https://raw.githubusercontent.com/terraform-linters/tflint/master/install_linux.sh \
    | bash || echo "tflint install attempted"

WORKDIR /workspace

ENTRYPOINT []
CMD ["/bin/bash"]

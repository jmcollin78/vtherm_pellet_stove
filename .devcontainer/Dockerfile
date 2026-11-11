FROM python:3.14-bookworm

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl ffmpeg git jq libturbojpeg0-dev vim \
    && install -d -m 0755 /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod a+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -ms /bin/bash vscode
USER vscode

ENV PATH=/home/vscode/.local/bin:$PATH

RUN curl -fsSL https://openspec.dev/cli/install.sh | sh \
    && curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh \
    && openspec --version \
    && rtk --version

WORKDIR /workspace

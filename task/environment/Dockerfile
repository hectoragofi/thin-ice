FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

# The agent works as an unprivileged user in /app. It plays through the game's MCP tools only;
# the game itself (state, puzzles, opponent) lives in the separate `game` container.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash agent \
    && mkdir -p /app \
    && chown agent:agent /app

# OpenCode is preinstalled so a run does not spend minutes on setup. Harbor finds it and skips
# its own install; any other agent is installed by Harbor as usual.
USER agent
ENV NVM_DIR=/home/agent/.nvm
RUN curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.2/install.sh | bash \
    && . "$NVM_DIR/nvm.sh" \
    && nvm install 22 \
    && nvm alias default 22 \
    && npm install -g opencode-ai@1.19.5 \
    && opencode --version \
    && npm cache clean --force \
    && nvm cache clear
USER root

# Tools-only play: this root-owned managed config denies every OpenCode tool except reading
# files, the todo list and the game's own MCP tools. No shell, no file writing, no subagents,
# no web, no skills. Every move has to come from the model reasoning with the game's tools,
# not from a program it writes. The agent user cannot change it.
COPY opencode-managed.json /etc/opencode/opencode.json

ENV THINICE_URL=http://game:8000
WORKDIR /app

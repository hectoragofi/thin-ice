FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

# The agent works as an unprivileged user in /app. It gets Python and the `ice` client; the
# game itself (state, puzzles, opponent) lives in the separate `game` container.
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

# Reasoning-only play: this root-owned managed config switches off the agent's shell, file
# writing and web tools, so every move has to come from the model through the game's tools
# rather than from a search program it writes. The agent user cannot change it.
COPY opencode-managed.json /etc/opencode/opencode.json

COPY ice /usr/local/bin/ice
RUN chmod 755 /usr/local/bin/ice

ENV THINICE_URL=http://game:8000
# OpenCode's default per-turn output cap (32000) cuts a long thought off and ends the run.
# Raise it to the model's limit so a run ends by the agent's play, not by the harness.
ENV OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX=64000
WORKDIR /app

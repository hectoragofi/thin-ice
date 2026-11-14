FROM python:3.12-slim

# The agent works as an unprivileged user in /app. It gets Python and the `ice` client; the
# game itself (state, puzzles, opponent) lives in the separate `game` container.
RUN useradd --create-home --shell /bin/bash agent \
    && mkdir -p /app \
    && chown agent:agent /app

COPY ice /usr/local/bin/ice
RUN chmod 755 /usr/local/bin/ice

ENV THINICE_URL=http://game:8000
WORKDIR /app

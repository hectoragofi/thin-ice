FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

RUN pip install --no-cache-dir fastmcp==4.1.8

WORKDIR /srv
COPY . /srv/

EXPOSE 8000
CMD ["python", "server.py"]

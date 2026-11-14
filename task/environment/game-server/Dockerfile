FROM python:3.12-slim

RUN pip install --no-cache-dir fastmcp==4.1.8

WORKDIR /srv
COPY . /srv/

EXPOSE 8000
CMD ["python", "server.py"]

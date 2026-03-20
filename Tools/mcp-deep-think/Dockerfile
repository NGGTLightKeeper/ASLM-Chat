# Deep Think ultra-light sandbox
# Target: ~150-160 MB
# Purpose: text processing, data calculations, pattern search in large texts
# Base: Alpine (~5 MB) + Python 3.12 (~50 MB) + minimal pure-Python packages

FROM python:3.12-alpine

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN pip install --no-cache-dir \
    numpy==2.2.4 \
    beautifulsoup4==4.13.3 \
    python-dateutil==2.9.0 \
    regex==2024.11.6 \
    ujson==5.10.0 \
    && pip uninstall -y pip

WORKDIR /workspace

CMD ["tail", "-f", "/dev/null"]

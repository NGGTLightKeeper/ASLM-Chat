# Build: network on. Run: network on, no root, direct pip installs.

FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.title="sandbox" \
      org.aslm.oda.sandbox-runtime="container-v1" \
      sandbox.security=1

RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
        bash \
        build-essential \
        ca-certificates \
        chromium \
        chromium-driver \
        coreutils \
        file \
        ffmpeg \
        findutils \
        fonts-dejavu \
        fonts-liberation \
        fonts-noto-color-emoji \
        gawk \
        ghostscript \
        git \
        gnupg \
        grep \
        imagemagick \
        jq \
        libffi-dev \
        libssl-dev \
        make \
        openssh-client \
        pandoc \
        pkg-config \
        poppler-utils \
        procps \
        python3-dev \
        qpdf \
        sqlite3 \
        tar \
        tesseract-ocr \
        unzip \
        xz-utils \
        zip \
    && python3 -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && useradd --create-home --home-dir /home/sandbox --uid 1000 --shell /bin/bash sandbox \
    && mkdir -p /mnt/data/work \
    && chown -R sandbox:sandbox /mnt/data /home/sandbox \
    && printf '%s\n' 'export PATH="/home/sandbox/.local/bin:$PATH"' > /etc/profile.d/sandbox-path.sh \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/* /tmp/* \
    && rm -f /usr/bin/apt* \
    && rm -f /usr/bin/curl /usr/bin/wget

COPY sandbox/sandbox-run /usr/local/bin/sandbox-run

RUN sed -i 's/\r$//' /usr/local/bin/sandbox-run \
    && chmod +x /usr/local/bin/sandbox-run

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONIOENCODING=utf-8 \
    PYTHONUTF8=1 \
    SANDBOX_CMD_TIMEOUT=60 \
    CHROME_BIN=/usr/bin/chromium \
    PIP_CACHE_DIR=/tmp/pip-cache \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_USER=1 \
    PATH=/home/sandbox/.local/bin:/usr/local/bin:/usr/bin:/bin

USER sandbox
WORKDIR /mnt/data/work
ENTRYPOINT ["/usr/local/bin/sandbox-run"]

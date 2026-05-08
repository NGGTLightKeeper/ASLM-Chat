FROM python:3.11-slim-bookworm

LABEL org.aslm.sandbox.supervisor-runtime="container-v2"

ENV DEBIAN_FRONTEND=noninteractive \
    CUDA_VISIBLE_DEVICES= \
    NVIDIA_VISIBLE_DEVICES=void

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    build-essential \
    coreutils \
    curl \
    file \
    findutils \
    gawk \
    git \
    grep \
    iproute2 \
    less \
    libgl1 \
    libglib2.0-0 \
    procps \
    ripgrep \
    sed \
    sudo \
    tini \
    unzip \
    wget \
    zip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip

RUN pip install --no-cache-dir \
    matplotlib \
    numpy \
    opencv-python-headless \
    pandas \
    pillow \
    requests \
    scikit-image

# Create isolated environment for Supervisor.
RUN python3 -m venv /opt/sandbox-venv && \
    /opt/sandbox-venv/bin/pip install --no-cache-dir --upgrade pip \
        "fastmcp>=3.2.0,<4.0" \
        "pydantic>=2.0,<3.0" \
        setproctitle

COPY supervisor /opt/sandbox-src

RUN useradd --create-home --shell /bin/bash sandbox_user && \
    echo "sandbox_user ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/sandbox_user && \
    chmod 0440 /etc/sudoers.d/sandbox_user && \
    mkdir -p /workspace && \
    chown -R root:root /opt/sandbox-venv /opt/sandbox-src && \
    chmod -R a-w /opt/sandbox-venv /opt/sandbox-src

COPY docker/start-container.sh /usr/local/bin/start-container.sh

RUN sed -i 's/\r//' /usr/local/bin/start-container.sh && \
    chmod +x /usr/local/bin/start-container.sh

WORKDIR /workspace

ENTRYPOINT ["tini", "--"]
CMD ["/usr/local/bin/start-container.sh"]

FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    build-essential \
    coreutils \
    curl \
    ffmpeg \
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
    tesseract-ocr \
    tesseract-ocr-rus \
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
    pytesseract \
    requests \
    scikit-image

RUN pip install --no-cache-dir \
    faster-whisper \
    yt-dlp \
    youtube-transcript-api

# Pre-download Whisper small model — CPU mode, int8
RUN python3 -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"

COPY docker/start-container.sh /usr/local/bin/start-container.sh
RUN chmod +x /usr/local/bin/start-container.sh

WORKDIR /workspace

CMD ["/usr/local/bin/start-container.sh"]

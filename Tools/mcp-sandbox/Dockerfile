FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-dev \
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

RUN ln -s /usr/bin/python3 /usr/bin/python

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

# Pre-download Whisper small model so it's baked into the image
RUN python3 -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"

WORKDIR /workspace

CMD ["tail", "-f", "/dev/null"]

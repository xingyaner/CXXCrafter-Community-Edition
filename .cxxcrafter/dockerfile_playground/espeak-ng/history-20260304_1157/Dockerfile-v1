FROM gcr.io/oss-fuzz-base/base-builder@sha256:c099d3d710d12d5d9a39498463ff10973977d1c7a85e9a0fbe00c7f0a0fa9fb8

RUN apt-get update && apt-get install -y \
    autoconf \
    automake \
    libtool \
    pkg-config \
    make \
    g++ \
    git \
    wget \
    python3 \
    python3-pip \
    libpcaudio-dev \
    libsonic-dev \
    libpulse-dev \
    libasound2-dev

# Clone and build espeak-ng
RUN git clone --depth 1 https://github.com/espeak-ng/espeak-ng.git

WORKDIR espeak-ng

# Copy the build script
COPY build.sh $SRC/

# Set up the build environment
ENV ASAN_OPTIONS=detect_leaks=0
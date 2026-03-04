FROM gcr.io/oss-fuzz-base/base-builder@sha256:1051d1a0a51f82987e4fa36f85dd8cee525df635f8523ac35575086979625e67

ENV DEBIAN_FRONTEND=noninteractive

# Use faster mirrors
RUN sed -i 's|http://archive.ubuntu.com/ubuntu/|http://mirrors.aliyun.com/ubuntu/|g' /etc/apt/sources.list \
    && sed -i 's|http://security.ubuntu.com/ubuntu/|http://mirrors.aliyun.com/ubuntu/|g' /etc/apt/sources.list \
    && apt-get update \
    && apt-get upgrade -y

# Install essential build tools and Swift dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    software-properties-common \
    wget \
    curl \
    git \
    libatomic1 \
    libxml2 \
    libcurl4 \
    libedit2 \
    libsqlite3-0 \
    libc6-dev \
    binutils \
    libgcc-5-dev \
    libstdc++-5-dev \
    zlib1g-dev \
    libpython3.6 \
    tzdata \
    locales \
    libicu-dev \
    libblocksruntime0 \
    libncurses5 \
    pkg-config \
    python3 \
    python3-pip \
    netcat-openbsd \
    lsof \
    perl \
    && rm -rf /var/lib/apt/lists/*

# Install Swift toolchain
RUN SWIFT_VERSION=5.7.3 && \
    SWIFT_PLATFORM=ubuntu22.04 && \
    SWIFT_BRANCH=swift-${SWIFT_VERSION}-release && \
    SWIFT_ARCHIVE_NAME=swift-${SWIFT_VERSION}-RELEASE-${SWIFT_PLATFORM} && \
    SWIFT_URL=https://download.swift.org/${SWIFT_BRANCH}/${SWIFT_PLATFORM}/${SWIFT_ARCHIVE_NAME}.tar.gz && \
    \
    wget -q ${SWIFT_URL} && \
    tar xzf ${SWIFT_ARCHIVE_NAME}.tar.gz --directory / --strip-components=1 && \
    rm ${SWIFT_ARCHIVE_NAME}.tar.gz

# Set up Swift environment
ENV PATH="/usr/bin:${PATH}"
ENV SWIFTC="/usr/bin/swiftc"
ENV SWIFT="/usr/bin/swift"

# Clone the repository
RUN git clone --depth 1 https://github.com/apple/swift-nio.git

# Copy the build script
COPY build.sh $SRC/

# Set the working directory
WORKDIR $SRC/swift-nio
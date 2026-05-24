ARG UBUNTU_VERSION=24.04
ARG DEERFLOW_VERSION=0.1.0
ARG COMPAT_VERSION=1
ARG MIN_APP_VERSION=0.1.0
ARG PYTHON_VERSION=3.12
ARG NODE_VERSION=20

FROM ubuntu:${UBUNTU_VERSION} AS builder

ARG DEERFLOW_VERSION
ARG PYTHON_VERSION
ARG NODE_VERSION

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

FROM ubuntu:${UBUNTU_VERSION} AS runtime

ARG DEERFLOW_VERSION
ARG COMPAT_VERSION
ARG MIN_APP_VERSION
ARG PYTHON_VERSION
ARG NODE_VERSION
ARG UBUNTU_VERSION

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    git \
    curl \
    wget \
    ca-certificates \
    openssh-server \
    sudo \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
    python${PYTHON_VERSION} \
    python${PYTHON_VERSION}-venv \
    python3-pip \
    && rm -rf /var/lib/apt/lists/* \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python${PYTHON_VERSION} 1

COPY --from=builder /usr/bin/node /usr/bin/node
COPY --from=builder /usr/bin/npm /usr/bin/npm
COPY --from=builder /usr/lib/node_modules /usr/lib/node_modules
COPY --from=builder /usr/include/node /usr/include/node
RUN ln -sf /usr/lib/node_modules/npm/bin/npm-cli.js /usr/bin/npm 2>/dev/null || true

RUN groupadd -g 1000 sandbox \
    && useradd -m -u 1000 -g 1000 -s /bin/bash sandbox \
    && echo "sandbox ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers.d/sandbox \
    && chmod 0440 /etc/sudoers.d/sandbox \
    && mkdir -p /home/sandbox/workspace \
    && chown sandbox:sandbox /home/sandbox/workspace

RUN mkdir -p /run/sshd \
    && ssh-keygen -A \
    && rm -rf /root/.cache/pip \
    && rm -rf /root/.npm

COPY config/sshd_config /etc/ssh/sshd_config
COPY config/deerflow-init.sh /usr/local/bin/deerflow-init.sh
RUN chmod +x /usr/local/bin/deerflow-init.sh \
    && /usr/local/bin/deerflow-init.sh "${DEERFLOW_VERSION}" "docker-base" "${COMPAT_VERSION}" "${MIN_APP_VERSION}" "${PYTHON_VERSION}" "${NODE_VERSION}" "${UBUNTU_VERSION}"

RUN apt-get remove -y software-properties-common \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf \
    /var/lib/apt/lists/* \
    /usr/share/doc/* \
    /usr/share/man/* \
    /usr/share/info/* \
    /usr/share/lintian/* \
    /usr/share/common-licenses/* \
    /usr/share/bash-completion/* \
    /usr/share/zsh/* \
    /usr/share/locale/* \
    /var/cache/apt/* \
    /var/log/* \
    /root/.cache/pip \
    /root/.npm \
    /tmp/* \
    /var/tmp/* \
    /home/sandbox/.cache

RUN find /usr -type f -executable -exec strip --strip-unneeded {} + 2>/dev/null || true \
    && find /usr -name "*.so" -exec strip --strip-unneeded {} + 2>/dev/null || true \
    && find /usr -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true \
    && find /usr -type f -name "*.pyc" -delete 2>/dev/null || true \
    && find /usr -type f -name "*.pyo" -delete 2>/dev/null || true \
    && find /usr -type d -name tests -path "*/python*" -exec rm -rf {} + 2>/dev/null || true

USER sandbox
WORKDIR /home/sandbox/workspace

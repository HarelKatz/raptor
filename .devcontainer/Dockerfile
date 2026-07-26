# RAPTOR Devcontainer
# Autonomous Offensive/Defensive Research Framework
#
# This container provides all dependencies for the RAPTOR security research framework.
# Based on comprehensive audit of all agents, commands, skills, and packages.

FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

# The base image's `node` devcontainer-feature install path added a stale
# yarn apt source (NO_PUBKEY 62D54FD4003F6525, breaks apt-get update) AND
# the yarn 1.x package itself (/usr/bin/yarn). Remove both so the later
# `npm install -g yarn@1.22.22` step doesn't collide on aarch64 builds.
RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && (apt-get -y remove yarn || echo "yarn not installed - skipping removal")

# ============================================================================
# SYSTEM DEPENDENCIES
# Organized by component that needs them
# ============================================================================

RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y --no-install-recommends \
    #
    # --- Core Tools (all scripts, packages) ---
    python3-pip \
    python3-venv \
    #
    # --- Git (recon, static-analysis, crash-analysis-agent, raptor_agentic) ---
    git \
    #
    # --- Build Tools (function-tracing skill, crash-analysis agents, exploit validation) ---
    build-essential \
    gcc \
    g++ \
    make \
    cmake \
    autoconf \
    automake \
    libtool \
    libtool-bin \
    clang-format \
    #
    # --- GDB (crash-analyzer-agent, binary_analysis package, rr-debugger skill) ---
    gdb \
    gdb-multiarch \
    #
    # --- Binary Analysis (binary_analysis package) ---
    binutils \
    file \
    #
    # --- Network Tools (web package, github-forensics skills) ---
    curl \
    wget \
    #
    # --- rr Debugger Dependencies (crash-analysis agents - Linux x86_64 only) ---
    # rr itself installed separately below
    libcapnp-dev \
    #
    # --- TLS / distro detection (curl, nodesource, playwright deps installer) ---
    ca-certificates \
    lsb-release \
    # --- Misc ---
    jq \
    unzip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ============================================================================
# SEMGREP (static-analysis, scan, raptor-scan, agentic commands)
# ============================================================================

# 1.171.0, not 1.161.0: semgrep 1.161.0 requires click~=8.1.8 (>=8.1.8,<8.2)
# while typer==0.25.1 (a root dependency) requires click>=8.2.1 — an EMPTY
# intersection. That only stayed invisible because semgrep and the project
# deps were two separate `pip install` layers, so two independent resolver
# runs each succeeded and the second silently upgraded click to 8.4.2, leaving
# the image failing its own `pip check`:
#   semgrep 1.161.0 has requirement click~=8.1.8, but you have click 8.4.2
# A single resolver pass over both is ResolutionImpossible, which is exactly
# what uv does, so the migration would have hit it as a hard failure.
# semgrep 1.171.0 widened the constraint to click~=8.4.2, which intersects
# typer's floor at 8.4.2/8.4.3.
RUN pip install --no-cache-dir semgrep==1.171.0

# ============================================================================
# RR DEBUGGER (rr-debugger skill, crash-analysis agents)
# Linux x86_64 only - provides deterministic record-replay debugging
# NOTE: Requires --privileged container flag and kernel parameter configuration
# ============================================================================

RUN apt-get update && apt-get install -y --no-install-recommends rr=5.9.0-9 \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    || echo "rr not available on this architecture - skipping"

# Configure kernel for rr (automatically done in privileged container)
# If rr kernel config fails, run with devcontainer --privileged flag
RUN echo "# To enable rr, the devcontainer needs --privileged flag" \
    && echo "# Run: echo 1 | sudo tee /proc/sys/kernel/perf_event_paranoid" \
    && echo "# Or use devcontainer.json with: \"runArgs\": [\"--privileged\"]"

# ============================================================================
# AFL++ FUZZER (fuzzing package, fuzz/raptor-fuzz commands)
# ============================================================================

RUN apt-get update && apt-get install -y --no-install-recommends \
    afl++ \
    afl++-clang \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    || echo "AFL++ not available - skipping"

# ============================================================================
# CODEQL CLI (codeql package, codeql command)
# Downloaded from GitHub releases
# ============================================================================

ARG CODEQL_VERSION=2.15.5
RUN mkdir -p /opt/codeql \
    && curl -L "https://github.com/github/codeql-cli-binaries/releases/download/v${CODEQL_VERSION}/codeql-linux64.zip" -o /tmp/codeql.zip \
    && unzip /tmp/codeql.zip -d /opt \
    && rm /tmp/codeql.zip \
    && ln -s /opt/codeql/codeql /usr/local/bin/codeql

# ============================================================================
# PYTHON DEPENDENCIES
# ============================================================================

# uv, digest-pinned exactly as in .github/docker/ci-deps.Dockerfile. Bump both
# together. The binaries are musl-static, so independent of this base's glibc.
# NOTE: pip is deliberately left installed. "uv only" governs how RAPTOR
# manages its OWN dependencies; an interactive research image should still
# offer operators pip for ad-hoc installs.
COPY --from=ghcr.io/astral-sh/uv:0.11.32@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c \
     /uv /uvx /usr/local/bin/

COPY pyproject.toml uv.lock /tmp/

# One export covers what three separate installs used to: requirements-dev.txt
# (runtime + test/lint/type tooling), and packages/web/requirements.txt
# (beautifulsoup4 + playwright) which is now the `web` extra. Installed with
# --system so every operator invocation — bin/raptor, python -m ... — resolves
# without activating anything, and so uv never resolves at container run time.
# --frozen asserts uv.lock matches pyproject.toml rather than re-resolving.
RUN uv export --frozen --no-emit-project --directory /tmp \
        --extra web --extra smt --group dev -o /tmp/req-dev.txt \
    && uv pip install --system --no-cache -r /tmp/req-dev.txt \
    && rm -f /tmp/req-dev.txt /tmp/pyproject.toml /tmp/uv.lock

# Install Playwright browser + system deps via Playwright's own dep installer.
# Replaces a hand-rolled apt list that drifted out of sync with upstream Chromium deps.
RUN apt-get update \
    && python -m playwright install --with-deps chromium \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ============================================================================
# CLAUDE CLI (claude-code npm package)
# Required to run RAPTOR via bin/raptor
# ============================================================================

# Capture-then-execute the nodesource setup script so a curl failure isn't
# silently swallowed by the pipeline (curl | bash ignores curl's exit status).
# Node 24 is the current stable release, and is supported by the latest Claude CLI.
RUN curl -fsSL https://deb.nodesource.com/setup_24.x -o /tmp/nodesource_setup.sh \
    && bash /tmp/nodesource_setup.sh \
    && rm /tmp/nodesource_setup.sh \
    && apt-get install -y --no-install-recommends nodejs=24.15.0-1nodesource1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    && npm install -g @anthropic-ai/claude-code@2.1.163

# ============================================================================
# JS PACKAGE MANAGERS (npm-managed yarn — apt source + package removed above)
# ============================================================================

RUN npm install -g yarn@1.22.22 pnpm@11.8.0

# ============================================================================
# ENVIRONMENT CONFIGURATION
# ============================================================================

ENV PATH="/opt/codeql:${PATH}"
ENV GIT_TERMINAL_PROMPT=0
ENV PYTHONUNBUFFERED=1
# Ensure python can import repo packages when container runs
# Adds repo root and `packages/` so `import core`, `import binary_analysis`, etc. work
ENV PYTHONPATH="/workspaces/raptor:/workspaces/raptor/packages"

# ============================================================================
# WORKSPACE
# ============================================================================

WORKDIR /workspaces/raptor

# ============================================================================
# RUNTIME USER
# ============================================================================
# Default to the non-root vscode user from the base image (UID 1000).
# vscode has passwordless sudo for tools that genuinely need root (e.g. rr in
# --privileged containers). All build steps above run as root by inheritance.
USER vscode

# CI dependency image — requirements-dev.txt baked in so the Python
# unit-test tiers skip the per-job venv build + artifact download. That
# fan-out (one venv download per tier × ~14 tiers) is what queues under
# a concurrent-runner cap; running the tiers inside this image removes
# it. Rebuilt by .github/workflows/ci-deps-image.yml whenever
# requirements*.txt (or this Dockerfile) change.
#
# Base pinned to bookworm to match the devcontainer
# (mcr.microsoft.com/devcontainers/python:1-3.12-bookworm, glibc 2.36)
# so platform-sensitive wheels resolve identically — notably z3-solver
# 4.15.4.0's manylinux_2_34 wheel (see the cap rationale in
# requirements-dev.txt). PYTHON_VERSION here must track tests.yml's
# env.PYTHON_VERSION (3.12).
FROM python:3.12-slim-bookworm

# OCI labels surface on the GHCR package page. `description` is the only
# per-package text GHCR renders (it has no per-image README upload — the
# package page otherwise shows the repo's main README), so use it to make
# clear this image is internal CI plumbing, not a RAPTOR distributable.
LABEL org.opencontainers.image.source="https://github.com/gadievron/raptor" \
      org.opencontainers.image.title="raptor-ci-deps" \
      org.opencontainers.image.description="RAPTOR INTERNAL CI build-cache image (GitHub Actions unit-test tiers). NOT a RAPTOR distributable or end-user artifact — do not pull or depend on this image."

# git is required by actions/checkout when this image is used as a
# container-job base — the slim base ships none, and checkout fails
# without it. coccinelle provides /usr/bin/spatch for the source_intel
# tier's real-spatch E2E tests. ca-certificates is already present in
# the slim image. Tiers that require heavier system tooling (sandbox
# namespaces, radare2/gcc) stay on the runner rather than bloating
# this image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git coccinelle \
    && rm -rf /var/lib/apt/lists/*

# uv, for the reconcile fallback in _tier.yml and (from the uv migration
# onward) the dependency install itself. Pinned by DIGEST rather than tag:
# the rest of this repo SHA-pins actions but only tag-pins images, and a
# tag is mutable — for a binary that is executed during CI in a
# supply-chain security tool, the stricter pin is the right default.
# The binaries are musl-static, so they are independent of the base's
# glibc; the digest is multi-arch (linux/amd64 + linux/arm64), which
# matters because this base is bookworm-pinned for z3's aarch64 wheel.
# Bump the digest and the tag together — the tag is documentation.
COPY --from=ghcr.io/astral-sh/uv:0.11.32@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c \
     /uv /uvx /usr/local/bin/

WORKDIR /opt/raptor-ci

# Copy only the manifests first so the dependency layer cache survives
# source-only changes to the repo.
COPY requirements.txt requirements-dev.txt ./

RUN pip install --no-cache-dir -r requirements-dev.txt \
    && sha256sum requirements.txt requirements-dev.txt > /etc/raptor-ci-deps.hash

# Build-time smoke import: fail the IMAGE build (not downstream CI) if a
# pinned dependency can't import on this base.
RUN python -c "import pytest, requests, pydantic, yaml, bs4, z3, defusedxml, packaging, tabulate, typer, instructor"

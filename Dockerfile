ARG PYTHON_IMAGE=python:3.10-slim@sha256:bb5bd66c26727f4f5b5557f24fb6024d57e44c22e6c81bcec522777bad8ac586
ARG DEBIAN_SNAPSHOT=20260824T000000Z
ARG GIT_PACKAGE_VERSION=1:2.47.3-0+deb13u1
ARG GIT_RUNTIME_VERSION=2.47.3
FROM ${PYTHON_IMAGE} AS builder

ARG SAMUEL_VERSION=0+unknown

WORKDIR /build
COPY requirements-container-build.lock ./
RUN python -m pip install --no-cache-dir --require-hashes \
    -r requirements-container-build.lock
COPY pyproject.toml LICENSE ./
COPY samuel ./samuel
RUN SETUPTOOLS_SCM_PRETEND_VERSION_FOR_SAMUEL="${SAMUEL_VERSION}" \
    python -m pip wheel --no-cache-dir --no-deps --no-build-isolation \
    --wheel-dir /dist .

FROM ${PYTHON_IMAGE} AS runtime

ARG PYTHON_IMAGE
ARG DEBIAN_SNAPSHOT
ARG GIT_PACKAGE_VERSION
ARG GIT_RUNTIME_VERSION
ARG SAMUEL_VERSION=0+unknown
ARG SAMUEL_REVISION=""
ARG SAMUEL_SOURCE_URL=""

LABEL org.opencontainers.image.title="S.A.M.U.E.L." \
      org.opencontainers.image.source="${SAMUEL_SOURCE_URL}" \
      org.opencontainers.image.version="${SAMUEL_VERSION}" \
      org.opencontainers.image.revision="${SAMUEL_REVISION}" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.base.name="${PYTHON_IMAGE}"

ENV SAMUEL_BUILD_REVISION="${SAMUEL_REVISION}" \
    SAMUEL_RUNTIME_CONFIG_DIR="/app/config"
WORKDIR /app

# Git is a required runtime dependency of the shipped worktree adapter.  Keep
# the slim Python base and resolve the exact Debian package only from the
# immutable snapshot already identified by that base image.
RUN sed -i \
      "s|URIs: http://deb.debian.org/debian-security|URIs: http://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT}|" \
      /etc/apt/sources.list.d/debian.sources \
    && sed -i \
      "s|URIs: http://deb.debian.org/debian|URIs: http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}|" \
      /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get -o Acquire::Check-Valid-Until=false install -y --no-install-recommends \
      git="${GIT_PACKAGE_VERSION}" \
    && test "$(git --version)" = "git version ${GIT_RUNTIME_VERSION}" \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r samuel && useradd -r -g samuel samuel

# Der Runtime-Lock wird mit Hashpflicht installiert. Das Projektwheel stammt
# aus der Builder-Stufe und wird ohne erneute Dependency-Aufloesung installiert.
COPY requirements-container.lock ./
RUN python -m pip install --no-cache-dir --require-hashes \
    -r requirements-container.lock
COPY --from=builder /dist/*.whl /tmp/samuel-wheel/
RUN python -m pip install --no-cache-dir --no-deps /tmp/samuel-wheel/*.whl \
    && rm -rf /tmp/samuel-wheel requirements-container.lock

# Nur ausgelieferte Default-Konfiguration gelangt ins Image. Operator-Secrets,
# Operator-Konfiguration und lokale Arbeitsdaten bleiben ausserhalb.
COPY config ./config

# Runtime-State und Worktrees sind getrennte, schreibbare Mountgrenzen.
# config/ wird read-only gemountet; Worktrees gehören nie ins State-Backup.
RUN mkdir -p /app/data/logs /samuel-workspaces \
    && chown -R samuel:samuel /app/data /samuel-workspaces

USER samuel
EXPOSE 7777

# Health bootstraps the installed runtime and performs bounded SCM checks.
# Allow cold starts on slower hosts to finish; failed checks still exit nonzero.
HEALTHCHECK --interval=30s --timeout=60s --start-period=10s --retries=3 \
    CMD samuel --config "${SAMUEL_RUNTIME_CONFIG_DIR}" health || exit 1

ENTRYPOINT ["samuel"]
CMD ["dashboard"]

FROM jenkins/jenkins:lts-jdk17

ARG DOCKER_VERSION=27.3.1
ARG COMPOSE_VERSION=2.29.7

USER root

RUN set -eux; \
    arch="$(uname -m)"; \
    curl -fsSL "https://download.docker.com/linux/static/stable/${arch}/docker-${DOCKER_VERSION}.tgz" -o /tmp/docker.tgz; \
    tar -xzf /tmp/docker.tgz -C /tmp; \
    install -m 0755 /tmp/docker/docker /usr/local/bin/docker; \
    rm -rf /tmp/docker /tmp/docker.tgz; \
    mkdir -p /usr/local/lib/docker/cli-plugins; \
    curl -fsSL "https://github.com/docker/compose/releases/download/v${COMPOSE_VERSION}/docker-compose-linux-${arch}" \
        -o /usr/local/lib/docker/cli-plugins/docker-compose; \
    chmod 0755 /usr/local/lib/docker/cli-plugins/docker-compose; \
    docker --version; \
    docker compose version

COPY entrypoint.sh /usr/local/bin/jenkins-docker-entrypoint.sh
RUN chmod 0755 /usr/local/bin/jenkins-docker-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/jenkins-docker-entrypoint.sh"]

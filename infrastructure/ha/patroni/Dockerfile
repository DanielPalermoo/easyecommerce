FROM postgres:15-bookworm

ARG PATRONI_VERSION=4.1.5

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-venv \
        ca-certificates \
    && python3 -m venv /opt/patroni \
    && /opt/patroni/bin/pip install --no-cache-dir \
        "patroni[etcd3,psycopg3]==${PATRONI_VERSION}" \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /etc/patroni && chown postgres:postgres /etc/patroni
ENV PATH="/opt/patroni/bin:${PATH}"
ENV PGDATA="/var/lib/postgresql/data"

USER postgres

ENTRYPOINT ["patroni"]
CMD ["/etc/patroni/patroni.yml"]


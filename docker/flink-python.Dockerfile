ARG FLINK_BASE_IMAGE=flink:1.18.1-java11
FROM ${FLINK_BASE_IMAGE}

ARG FLINK_KAFKA_CONNECTOR_VERSION=3.1.0-1.18

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl python3 python3-pip \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/flink.txt /tmp/flink-requirements.txt
RUN python3 -m pip install --no-cache-dir -r /tmp/flink-requirements.txt \
    && curl -fsSL \
        "https://repo.maven.apache.org/maven2/org/apache/flink/flink-sql-connector-kafka/${FLINK_KAFKA_CONNECTOR_VERSION}/flink-sql-connector-kafka-${FLINK_KAFKA_CONNECTOR_VERSION}.jar" \
        -o "/opt/flink/lib/flink-sql-connector-kafka-${FLINK_KAFKA_CONNECTOR_VERSION}.jar"
USER flink

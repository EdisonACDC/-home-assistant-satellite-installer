ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.12-alpine3.20
FROM ${BUILD_FROM}
RUN pip install --no-cache-dir flask==3.0.3
COPY app /app
COPY run.sh /run.sh
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]

FROM python:3.13.18-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OUTPUT_DIR=/output

WORKDIR /src
COPY pyproject.toml README.md MANIFEST.in LICENSE ./
COPY config/requirements.txt config/requirements.txt
COPY wayback_archive wayback_archive
RUN pip install --no-cache-dir . \
    && rm -rf /src

RUN useradd --create-home --uid 1000 wayback \
    && mkdir /output \
    && chown wayback:wayback /output

USER wayback
WORKDIR /output
VOLUME /output

ENTRYPOINT ["wayback-archive"]

FROM python:3.12.12-alpine3.22@sha256:848ba4413eb897e225159b8fc1b02094576cbae4aa73fc13142608ae2c8c0e32 AS builder
WORKDIR /build
COPY pyproject.toml ./
COPY src ./src
RUN python -m pip wheel --timeout 120 --no-deps --wheel-dir /wheels .

FROM python:3.12.12-alpine3.22@sha256:848ba4413eb897e225159b8fc1b02094576cbae4aa73fc13142608ae2c8c0e32
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-index --no-deps /wheels/*.whl && rm -rf /wheels
USER 10001:10001
EXPOSE 8080
CMD ["aks-pilot-demo"]

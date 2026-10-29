FROM python:3.12.12-alpine3.22@sha256:848ba4413eb897e225159b8fc1b02094576cbae4aa73fc13142608ae2c8c0e32
WORKDIR /app
COPY server.py .
USER 10001:10001
EXPOSE 8080
CMD ["python", "server.py"]

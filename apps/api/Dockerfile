# Image API + worker + migrasi SINERGI.
FROM python:3.12.8-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
COPY . ./
RUN pip install . && rm -rf /src/build
RUN useradd --system --uid 10001 --home /nonexistent sinergi
USER sinergi
WORKDIR /app
EXPOSE 8000
CMD ["uvicorn", "--factory", "sinergi_api.app.main:buat_app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]

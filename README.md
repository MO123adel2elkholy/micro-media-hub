# Media Processing Microservices App

A lightweight event-driven microservices project for uploading videos, converting them to MP3, storing files in MongoDB GridFS, and notifying users by email.

Supported
- Python 3.10
- Flask, PyMongo, Pika
- RabbitMQ, MongoDB, ffmpeg
- Docker / docker-compose

Quick summary
- Gateway: receives uploads, saves video to GridFS, publishes a "video" job.
- Converter: consumes "video" jobs, converts to MP3, stores MP3 to GridFS, publishes "mp3" job.
- Notification: consumes "mp3" jobs and sends email notifications.

Contents
- micro-media-hub/
  - gateway-service/
  - converter-service/
  - notification-service/
  - requirements.txt
  - .env.example
  - docker-compose.yml (optional)

## Quick Start (local)

Recommended .env placement
- Copy micro-media-hub/.env.example -> micro-media-hub/.env
- When running docker-compose from the repository root, reference micro-media-hub/.env in docker-compose.yml or with --env-file.

Start everything (from repo root)
```powershell
docker-compose -f micro-media-hub/docker-compose.yml up --build
```

Build and run a single service (from repo root)
```powershell
cd micro-media-hub\notification-service
docker build -t notification-service:local .
# run with env file located at micro-media-hub\.env (relative path from service folder)
docker run --env-file ..\.env -p 8000:8000 notification-service:local
```

Or run from the micro-media-hub folder
```powershell
cd micro-media-hub
docker-compose up --build
```

Verify services
- MongoDB: mongodb://localhost:27017
- RabbitMQ management UI: http://localhost:15672 (guest/guest default)

Example docker-compose (micro-media-hub/docker-compose.yml)
```yaml
version: "3.8"
services:
  mongo:
    image: mongo:5
    ports: ["27017:27017"]
  rabbit:
    image: rabbitmq:3-management
    ports: ["5672:5672","15672:15672"]
  notification-service:
    build: ./notification-service
    env_file: ./.env
    depends_on:
      - mongo
      - rabbit
```

## .env.example

```env
# filepath: micro-media-hub/.env.example
PYTHONUNBUFFERED=1

# MongoDB
MONGODB_VIDEOS_URI=mongodb://localhost:27017/videos
MONGODB_MP3S_URI=mongodb://localhost:27017/mp3s

# RabbitMQ
RABBITMQ_URL=amqp://guest:guest@rabbit:5672/

# SMTP (for notifications)
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=you@example.com
SMTP_PASS=secret
```

Notes on .env locations
- Use micro-media-hub/.env for local development.
- If running container with docker run, pass --env-file pointing to the file you created.
- CI should supply secrets via the platform secret store; do not commit .env.

## Health check

- notification-service/health_check.py (used by Docker HEALTHCHECK)
  - Loads .env
  - Pings videos and mp3 MongoDB URIs
  - Attempts RabbitMQ connection
  - Prints JSON {"services": {...}} and exits 0 if all OK, non-zero otherwise

Dockerfile example uses:
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python /app/health_check.py

## Message formats

Video queue (video -> converter)
```json
{ "video_fid": "<gridfs_id>", "username": "user@example.com" }
```

MP3 queue (converter -> notification)
```json
{
  "event": "video_converted",
  "status": "success",
  "video_fid": "<gridfs_id>",
  "mp3_fid": "<gridfs_id>",
  "username": "user@example.com"
}
```

## Reliability & delivery

- Use durable queues: queue_declare(queue, durable=True)
- Publish persistent messages: pika.BasicProperties(delivery_mode=2)
- ACK on success, NACK with requeue for transient failures
- Recommended: Dead-letter queue (DLQ) for permanent failures and retry/backoff policies

## Tests & CI

Local dev environment (Windows PowerShell)
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1    # PowerShell
pip install -r micro-media-hub\requirements.txt
python -m pytest micro-media-hub\tests -q
```

If using cmd.exe activate with:
```powershell
.venv\Scripts\activate.bat
```

Minimal GitHub Actions CI (save as .github/workflows/ci.yml)
```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          pip install -r micro-media-hub/requirements.txt
      - name: Run tests
        run: python -m pytest micro-media-hub/tests -q
  build:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - name: Build notification image
        run: docker build -t notification-service:ci micro-media-hub/notification-service
```

## Metrics & logging

- Expose Prometheus metrics at /metrics (recommended) and add structured JSON logs.
- Example Prometheus scrape config:
```yaml
scrape_configs:
  - job_name: 'notification-service'
    static_configs:
      - targets: ['notification-service:8000']
```
- If not implemented, add a /metrics endpoint in each service before production.

## Production recommendations (short)

- Centralize secrets (Vault / cloud secrets)
- Add structured logging and metrics (Prometheus/Grafana)
- Harden SMTP (rate limits, retries)
- Configure DLQ and retry/backoff
- Add health endpoints and readiness/liveness probes
- Add idempotency checks for message handlers

## Project structure (example)
```
micro-media-hub/
├─ .env.example
├─ docker-compose.yml
├─ requirements.txt
├─ gateway-service/
|__ auth-service/
├─ converter-service/
└─ notification-service/
   ├─ consumer.py
   ├─ health_check.py
   └─ Dockerfile
```

## License & Contributing

- Add LICENSE (e.g., MIT) and CONTRIBUTING.md to the repo root.
- Suggested files to add:
  - LICENSE (MIT)
  - CONTRIBUTING.md (branch/PR/testing guidelines)
  - CODE_OF_CONDUCT.md

## Checklist before production

- [ ] Validate env values in CI and do not commit secrets
- [ ] Add monitoring + alerting
- [ ] Add rate limiting and quota checks on gateway
- [ ] Configure DLQ for failed messages
- [ ] Harden SMTP and secret handling
- [ ] Add CI badges to top of this README


# YouTube RSS Watcher

A production-ready FastAPI service that polls YouTube RSS feeds on a configurable interval, persists seen videos in PostgreSQL, caches lookups in Redis, and sends Telegram notifications when a tracked channel drops a new video.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     FastAPI App                         │
│                                                         │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────┐  │
│  │ Background   │   │  REST API    │   │  /healthz  │  │
│  │ Poller       │   │  /api/v1/... │   │  (probes)  │  │
│  └──────┬───────┘   └──────────────┘   └────────────┘  │
│         │                                               │
│         ▼  every POLL_INTERVAL_SECONDS                  │
│  ┌──────────────┐                                       │
│  │ YouTube RSS  │──► xmltodict parse                    │
│  │ Feed Fetch   │                                       │
│  └──────┬───────┘                                       │
│         │                                               │
│         ▼  deduplication                                │
│  ┌──────────────┐    hit?  ┌──────────────┐            │
│  │  Redis Cache │─────────►│   skip       │            │
│  └──────┬───────┘          └──────────────┘            │
│         │ miss                                          │
│         ▼                                               │
│  ┌──────────────┐    seen? ┌──────────────┐            │
│  │  PostgreSQL  │─────────►│   backfill   │            │
│  │  seen_videos │          │   Redis      │            │
│  └──────┬───────┘          └──────────────┘            │
│         │ new!                                          │
│         ▼                                               │
│  ┌──────────────┐   ┌──────────────────────────────┐   │
│  │  Telegram    │   │  Persist to DB + Redis        │   │
│  │  Notifier    │   └──────────────────────────────┘   │
│  └──────────────┘                                       │
└─────────────────────────────────────────────────────────┘
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | — | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | ✅ | — | Your personal or group chat ID |
| `YOUTUBE_CHANNEL_IDS` | ✅ | — | Comma-separated channel IDs |
| `DATABASE_URL` | ✅ | — | asyncpg connection string |
| `REDIS_URL` | ✅ | — | Redis connection URL |
| `POLL_INTERVAL_SECONDS` | ❌ | `900` | Seconds between RSS polls. Must be integer > 0 |

### Finding a YouTube Channel ID

1. Go to the channel page on YouTube
2. View page source (`Ctrl+U`)
3. Search for `externalId` — the value is the channel ID (starts with `UC`)

---

## Local Development

```bash
# 1. Copy and fill env vars
cp .env.example .env

# 2. Start everything
docker compose up --build

# 3. View API docs
open http://localhost:8000/docs
```

### .env.example
```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
YOUTUBE_CHANNEL_IDS=UCxxxxxx,UCyyyyyy
POLL_INTERVAL_SECONDS=60   # 1 min in dev
```

---

## Kubernetes Deployment

### 1. Create the namespace and config

```bash
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/02-configmap.yaml   # edit channel IDs first
```

### 2. Create the Secret (never commit real values)

```bash
kubectl create secret generic yt-watcher-secrets \
  --from-literal=telegram-bot-token='8788414582:AAGd6BJmdTZnn1zklFzhzbwELG8tmJwQyE4' \
  --from-literal=telegram-chat-id='451648606' \
  --from-literal=postgres-password='your-secure-db-password' \
  -n yt-watcher
```

### 3. Deploy infrastructure

```bash
kubectl apply -f k8s/03-postgres.yaml
kubectl apply -f k8s/04-redis.yaml
```

### 4. Build and push your image

```bash
docker build -t your-registry/yt-watcher:latest .
docker push your-registry/yt-watcher:latest
```

Update `image:` in `k8s/05-deployment.yaml`, then:

```bash
kubectl apply -f k8s/05-deployment.yaml
```

### 5. Verify

```bash
kubectl get pods -n yt-watcher
kubectl logs -f deployment/yt-watcher -n yt-watcher
```

---

## Changing the Poll Interval (zero downtime)

```bash
# Edit the ConfigMap
kubectl edit configmap yt-watcher-config -n yt-watcher
# Change POLL_INTERVAL_SECONDS value, save

# Restart the pod to pick up the new value
kubectl rollout restart deployment/yt-watcher -n yt-watcher
```

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/healthz` | Liveness/readiness probe |
| `GET` | `/api/v1/status` | Runtime config (interval, channels, Telegram status) |
| `GET` | `/api/v1/videos` | List all seen videos (supports `?channel_id=` and `?limit=`) |
| `POST` | `/api/v1/poll` | Manually trigger an immediate poll cycle |
| `DELETE` | `/api/v1/videos/{video_id}` | Remove from seen list (triggers re-notification on next poll) |

Full interactive docs: `http://localhost:8000/docs`

---

## Deduplication Strategy

Two-layer deduplication prevents duplicate Telegram messages:

1. **Redis** (fast path) — O(1) lookup, 30-day TTL. Survives app restarts.
2. **PostgreSQL** (slow path / source of truth) — catches videos that fell out of Redis. On DB hit, backfills Redis to keep the cache warm.

A video is only notified **once**, even across pod restarts, Redis flushes, or replica scaling.

---

## Security Notes

- Secrets are kept out of ConfigMaps and never committed to git
- App runs as a non-root user (`uid=1000`) inside the container
- Consider [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets) or [External Secrets Operator](https://external-secrets.io/) for GitOps workflows
- The Telegram token in this repo is a **live credential** — rotate it via @BotFather after testing

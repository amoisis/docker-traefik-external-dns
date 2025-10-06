[![Docker](https://github.com/amoisis/docker-traefik-external-dns/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/amoisis/docker-traefik-external-dns/actions/workflows/docker-publish.yml)

# DNS Automation with Traefik

This project provides a **lightweight DNS automation service** that syncs Traefik routes directly to your DNS provider.  
It’s designed for **resilient, self-healing deployments** with caching, retry/backoff logic, and flexible TTL support.

---

## Features

- **Dynamic DNS Sync**: Automatically updates DNS records from Traefik host rules.
- **Deduplication & Filtering**: Ignores wildcards and applies domain allow/deny lists.
- **Dynamic IP Discovery**: Resolves container IPs for A and CNAME records.
- **Persistent Cache**: Prevents redundant writes and supports fast recovery.
- **Flexible TTLs**: Configurable per-record or global defaults.
- **Debug & Health Endpoints**: `/healthz`, `/metrics` for observability.
- **Retry/Backoff Logic**: Handles transient DNS or API errors gracefully.
- **Event-Driven Triggers**: Reacts to Traefik route changes with minimal delay.

---

## Run with Docker Compose

[Docker Compose](docker-compose-example.yaml)

## Verify
- Visit http://localhost:8888/healthz → should return OK.
- Visit Visit http://localhost:8888/records for discovered routes
- Check logs for synced records.

## Configuration

|      Variable      |            Description            |            Example           |
|--------------------|-----------------------------------|------------------------------|
| `TRAEFIK_API`      | API that returns the Traefik routes  | http://traefik:8080/api/http/routers          |
| `TRAEFIK_HOSTNAME` | A record to lookup for Traefik  | traefik.example.com                           |
| `WEBHOOK`          | Webhook to update dns       | http://external-dns-unifi:8888/record         |
| `REFRESH_INTERVAL` | Refresh interval in seconds       | 300                                           |
| `LOG_LEVEL`        | Set the log level for the application | INFO | 
| `CACHE_FILE`       | Cache file. Delete this if a full refresh is required | /data/last_endpoints.json |
| `ALLOWED_DOMAINS`  | Filter Traefik domain tagets accepts comma seperated and wilcards | *.example.com |
| `IGNORED_DOMAINS`  | Ignore domains. This integration will delete anything that is not a discovered Traefik route. Helpful to have the Traefik A record in here | traefik.example.com |
| `DEFAULT_TTL`      | This can be set to auto or an integar |"Auto"|
| `MAX_RETRIES`      | Max retries before application stops|                 5      |
| `BACKOFF_FACTOR`   | Backoff factor in seconds | 2 |

## Troubleshooting
- Ensure your traefik record is an A record
- Records Not Updating
  -  Check /cache endpoint for stale entries.
- Startup Reliability
  - Retry/backoff logic ensures recovery, but you can add depends_on in Compose to sequence Traefik startup


## Roadmap
- [ ] Multi-provider, current works with external-dns-unifi-webhook
- [ ] Webhook-based event triggers
- [ ] UI dashboard for record inspection

##  Contributing
Contributions are welcome!
- Fork the repo
- Create a feature branch
- Submit a PR with clear commit messages

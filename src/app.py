import requests, socket, re, os, time, json, threading, sys
from flask import Flask, jsonify
import fnmatch
import dns.resolver

# ---------------- Config ---------------- #
TRAEFIK_API = os.getenv("TRAEFIK_API", "http://traefik:8080/api/http/routers")
TRAEFIK_HOSTNAME = os.getenv("TRAEFIK_HOSTNAME", "traefik")
WEBHOOK = os.getenv("WEBHOOK", "http://external-dns-unifi:8888/records")
REFRESH_INTERVAL = int(os.getenv("REFRESH_INTERVAL", "30"))
CACHE_FILE = os.getenv("CACHE_FILE", "/data/last_endpoints.json")
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG").upper()
ALLOWED_DOMAINS = [d.strip() for d in os.getenv("ALLOWED_DOMAINS", "").split(",") if d.strip()]
IGNORED_DOMAINS = [d.strip() for d in os.getenv("IGNORED_DOMAINS", "").split(",") if d.strip()]
DEFAULT_TTL = os.getenv("DEFAULT_TTL", "Auto")  # can be "Auto" or an integer
MAX_RETRIES = os.getenv("MAX_RETRIES", "5")
BACKOFF_FACTOR = os.getenv("BACKOFF_FACTOR", "2")  # exponential backoff: 1s, 2s, 4s, 8s, 16s

app = Flask(__name__)

app.logger.setLevel(LOG_LEVEL)

# ---------------- Helpers ---------------- #
def allowed_domain(host):
    if any(fnmatch.fnmatch(host, pattern) for pattern in IGNORED_DOMAINS):
        return False
    if ALLOWED_DOMAINS:
        return any(fnmatch.fnmatch(host, pattern) for pattern in ALLOWED_DOMAINS)
    return True

def resolve_ttl():
    if DEFAULT_TTL.lower() == "auto":
        return None
    try:
        return int(DEFAULT_TTL)
    except ValueError:
        app.logger.warning(f"Invalid TTL '{DEFAULT_TTL}', falling back to 300")
        return 300

def build_endpoints():
    resp = requests.get(TRAEFIK_API, timeout=5)
    resp.raise_for_status()
    routers = resp.json()
    ttl = resolve_ttl()
    endpoints = {}
    for router in routers:
        rule = router.get("rule", "")
        hosts = re.findall(r"Host(?:Regexp)?\(`([^`]*)`\)", rule)
        for host in hosts:
            if not allowed_domain(host):
                continue
            if "." not in host:
                app.logger.debug(f"Skipping non-FQDN host: {host}")
                continue

            record = {
                "dnsName": host,
                "recordType": "CNAME",
                "targets": [TRAEFIK_HOSTNAME]
            }
            if ttl is not None:
                record["recordTTL"] = ttl
            endpoints[host] = record
    return endpoints

def diff_endpoints(old, new):
    create, update_old, update_new, delete = [], [], [], []
    for name, ep in new.items():
        if name not in old:
            create.append(ep)
        elif old[name] != ep:
            update_old.append(old[name])
            update_new.append(ep)
    for name, ep in old.items():
        if name not in new:
            delete.append(ep)
    return create, update_old, update_new, delete

# ---------------- Retry/Backoff Wrapper ---------------- #
def push_to_unifi(create, update_old, update_new, delete):
    payload = {
        "Create": create,
        "UpdateOld": update_old,
        "UpdateNew": update_new,
        "Delete": delete
    }
    headers = {
        "Content-Type": "application/external.dns.webhook+json;version=1"
    }
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.post(WEBHOOK, headers=headers, json=payload, timeout=10)
            r.raise_for_status()
            app.logger.info(
                f"Pushed changes: +{len(create)} ~{len(update_new)} -{len(delete)} "
                f"(attempt {attempt})"
            )
            return
        except Exception as e:
            wait = BACKOFF_FACTOR ** (attempt - 1)
            app.logger.warning(f"Push attempt {attempt} failed: {e}. Retrying in {wait}s...")
            time.sleep(wait)
    app.logger.error("All retries failed when pushing to webhook")

# ---------------- Cache ---------------- #
def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                return json.load(f)
        except Exception as e:
            app.logger.warning(f"Failed to load cache: {e}")
    return {}

def save_cache(state):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(state, f)
        app.logger.debug(f"Cache saved to {CACHE_FILE}")
    except Exception as e:
        app.logger.error(f"Failed to save cache: {e}")

# ---------------- Background Loop ---------------- #
def refresh_loop():
    app.logger.info("Refresh")
    last_endpoints = load_cache()
    while True:
        try:
            new_endpoints = build_endpoints()
            c, uo, un, d = diff_endpoints(last_endpoints, new_endpoints)
            if c or uo or d:
                push_to_unifi(c, uo, un, d)
                save_cache(new_endpoints)
            else:
                app.logger.debug("No DNS changes detected")
        except Exception as e:
            app.logger.error(f"Sync failed: {e}")
        time.sleep(REFRESH_INTERVAL)

# ---------------- Flask Endpoints ---------------- #
@app.route("/records", methods=["GET"])
def records():
    app.logger.info("/records endpoint called")
    try:
        endpoints = build_endpoints()
        return jsonify(list(endpoints.values()))
    except Exception as e:
        app.logger.error(f"Error occurred in /records: {e}", exc_info=True)
        return jsonify({"error": "An internal error has occurred."}), 500

@app.route("/healthz", methods=["GET"])
def healthz():
    app.logger.info("/healthz endpoint called")
    return jsonify({"status": "ok"}), 200

# ---------------- Entrypoint ---------------- #
if __name__ == "__main__":
    try:
        answers = dns.resolver.resolve(TRAEFIK_HOSTNAME, 'A')
        if not answers:
            print(f"ERROR: No A record found for {TRAEFIK_HOSTNAME}", file=sys.stderr)
            sys.exit(1)
        app.logger.info(f"Successfully resolved {TRAEFIK_HOSTNAME} to {', '.join([r.to_text() for r in answers])}")
    except dns.resolver.NXDOMAIN:
        print(f"ERROR: {TRAEFIK_HOSTNAME} does not exist.", file=sys.stderr)
        sys.exit(1)
    except dns.resolver.NoAnswer:
        print(f"ERROR: No A record found for {TRAEFIK_HOSTNAME}", file=sys.stderr)
        sys.exit(1)
    except dns.resolver.Timeout:
        print(f"ERROR: DNS query timed out for {TRAEFIK_HOSTNAME}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected DNS error occurred: {e}", file=sys.stderr)
        sys.exit(1)

    app.logger.info("Application started")
    threading.Thread(target=refresh_loop, daemon=True).start()
    from waitress import serve
    serve(app, host="0.0.0.0", port=8888)

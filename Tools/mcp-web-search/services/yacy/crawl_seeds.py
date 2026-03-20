# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

YACY_URL = "http://localhost:8090"
YACY_USER = "admin"
YACY_PASS = "admin123"
SEEDS_FILE = Path(__file__).parent / "seeds.json"
DELAY_BETWEEN_STARTS = 3

PAGINATED_DOMAINS = {
    "habr.com",
    "stackoverflow.com",
    "serverfault.com",
    "unix.stackexchange.com",
    "superuser.com",
    "ru.stackoverflow.com",
    "4pda.to",
    "bbs.archlinux.org",
    "www.linux.org.ru",
    "medium.com",
    "www.opennet.ru",
}


# Seed loading helpers.
# Load configured crawl seeds.
def load_seeds(collection_filter: str | None = None) -> list[dict]:
    """Load the seed list and optionally keep one collection only."""

    raw = SEEDS_FILE.read_text(encoding="utf-8")
    data = json.loads(raw)
    seeds = data.get("seeds", [])

    if collection_filter:
        seeds = [seed for seed in seeds if seed["collection"] == collection_filter]

    return seeds


# YaCy availability helpers.
# Check whether YaCy is reachable.
def check_yacy() -> bool:
    """Check whether the local YaCy instance is reachable."""

    try:
        response = requests.get(
            f"{YACY_URL}/api/status_p.xml",
            auth=HTTPBasicAuth(YACY_USER, YACY_PASS),
            timeout=5,
        )
        if response.status_code == 401:
            response = requests.get(
                f"{YACY_URL}/api/status_p.xml",
                auth=HTTPDigestAuth(YACY_USER, YACY_PASS),
                timeout=5,
            )
        return response.status_code == 200
    except requests.RequestException:
        return False


# YaCy availability helpers.
# Read the current crawler status.
def get_crawler_status() -> dict:
    """Read a minimal crawler status snapshot from the YaCy API."""

    try:
        response = requests.get(
            f"{YACY_URL}/api/status_p.xml",
            auth=HTTPBasicAuth(YACY_USER, YACY_PASS),
            timeout=5,
        )
        if response.status_code == 401:
            response = requests.get(
                f"{YACY_URL}/api/status_p.xml",
                auth=HTTPDigestAuth(YACY_USER, YACY_PASS),
                timeout=5,
            )

        active = re.search(r"activeCount>(\d+)<", response.text)
        queue = re.search(r"queueSize>(\d+)<", response.text)
        indexed = re.search(r"indexDocCount>(\d+)<", response.text)
        return {
            "active": int(active.group(1)) if active else "?",
            "queue": int(queue.group(1)) if queue else "?",
            "indexed": int(indexed.group(1)) if indexed else "?",
        }
    except Exception as error:
        return {"error": str(error)}


# Crawl launch helpers.
# Submit one seed crawl to YaCy.
def start_crawl(seed: dict, force_recrawl: bool = False) -> bool:
    """Submit one seed URL to the YaCy crawler."""

    domain = urlparse(seed["url"]).netloc.removeprefix("www.")
    allow_query = domain in PAGINATED_DOMAINS
    cache_policy = "recrawl" if force_recrawl else "iffresh"

    params = {
        "crawlingstart": "",
        "crawlingMode": "url",
        "crawlingURL": seed["url"],
        "crawlingDepth": str(seed.get("depth", 2)),
        "range": "domain",
        "crawlingDomMaxPages": "100000",
        "crawlingQ": "on" if allow_query else "off",
        "noindexWhenCanonicalUnequalURL": "on",
        "indexText": "on",
        "indexMedia": "off",
        "storeHTCache": "on",
        "cachePolicy": cache_policy,
        "recrawlIfOlder": "0" if force_recrawl else "",
        "crawlerNoDepthWhenHead": "off",
        "collection": seed["collection"],
        "crawlerAgent": "YaCy/AI-Research",
    }

    try:
        auth = HTTPBasicAuth(YACY_USER, YACY_PASS)
        response = requests.get(
            f"{YACY_URL}/Crawler_p.html",
            params=params,
            auth=auth,
            timeout=60,
        )
        if response.status_code == 401:
            response = requests.get(
                f"{YACY_URL}/Crawler_p.html",
                params=params,
                auth=HTTPDigestAuth(YACY_USER, YACY_PASS),
                timeout=60,
            )
        return response.status_code == 200
    except requests.RequestException as error:
        print(f"    HTTP error: {error}")
        return False


# Command-line entry point.
# Parse arguments and run crawl jobs.
def main() -> None:
    """Parse arguments, validate YaCy, and start crawl jobs."""

    parser = argparse.ArgumentParser(description="YaCy Seed Crawler")
    parser.add_argument(
        "--collection",
        help="Run only the selected collection, for example: tech_vpn",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned actions without starting the crawler",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show the current YaCy crawler status",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DELAY_BETWEEN_STARTS,
        help=f"Delay between seed starts in seconds, default: {DELAY_BETWEEN_STARTS}",
    )
    parser.add_argument(
        "--recrawl",
        action="store_true",
        help=(
            "Run a deep recrawl with cachePolicy=recrawl and recrawlIfOlder=0.\n"
            "This revisits already indexed pages instead of limiting work to fresh content.\n"
            "Without this flag the crawler uses cachePolicy=iffresh."
        ),
    )
    args = parser.parse_args()

    if args.status:
        status = get_crawler_status()
        if "error" in status:
            print(f"Failed to connect to YaCy: {status['error']}")
            sys.exit(1)

        print("YaCy crawler status:")
        print(f"   Active crawl threads : {status['active']}")
        print(f"   Queue size           : {status['queue']}")
        print(f"   Total indexed docs   : {status['indexed']}")
        return

    seeds = load_seeds(args.collection)
    if not seeds:
        print(f"No seeds found for collection={args.collection!r}")
        sys.exit(1)

    print(f"Seeds found: {len(seeds)}")
    if args.collection:
        print(f"   Collection filter: [{args.collection}]")
    print()

    if args.dry_run:
        print("DRY RUN - crawler will not be started\n")
        for index, seed in enumerate(seeds, 1):
            print(f"  [{index:2d}] [{seed['collection']}] depth={seed['depth']}")
            print(f"       {seed['url']}")
            print(f"       {seed.get('description', '')}")
        return

    print("Checking YaCy connection...")
    if not check_yacy():
        print(f"YaCy is not reachable at {YACY_URL}")
        print("   Start it with: docker compose -f services/yacy/docker-compose.yml up -d")
        sys.exit(1)
    print(f"YaCy is reachable: {YACY_URL}\n")

    ok = 0
    fail = 0

    if args.recrawl:
        print("RECRAWL mode: cachePolicy=recrawl, revisiting older pages\n")
    else:
        print("IFFRESH mode: reuse fresh cache when possible for faster incremental crawling")
        print("   Use --recrawl for a full revisit\n")

    for index, seed in enumerate(seeds, 1):
        print(f"[{index:2d}/{len(seeds)}] [{seed['collection']}] {seed['url']}")
        print(f"         depth={seed['depth']} | {seed.get('description', '')}")

        success = start_crawl(seed, force_recrawl=args.recrawl)
        if success:
            print("         Started")
            ok += 1
        else:
            print("         Start failed")
            fail += 1

        if index < len(seeds):
            print(f"         Waiting {args.delay}s...")
            time.sleep(args.delay)

    print()
    print("Done")
    print(f"Started: {ok}")
    print(f"Failed:  {fail}")
    print()
    print("Check progress:")
    print("   python crawl_seeds.py --status")
    print("   http://localhost:8090/yacy/search.html")


if __name__ == "__main__":
    main()

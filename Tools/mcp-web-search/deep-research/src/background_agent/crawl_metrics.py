# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List

logger = logging.getLogger("background_agent.metrics")


# Per-domain metrics.
# Aggregated metrics for one domain.
@dataclass
class _DomainMetrics:
    """Metrics tracked for one domain."""

    requests: int = 0
    success: int = 0
    failed: int = 0
    blocked_429: int = 0
    blocked_403: int = 0
    errors_5xx: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    retries: int = 0
    parse_success: int = 0
    parse_failed: int = 0
    total_bytes: int = 0
    latencies: list = field(default_factory=list)


# Metrics collector.
# Crawl metrics collector.
class CrawlMetrics:
    # Initialize run-level metric storage.
    def __init__(self):
        self._domains: Dict[str, _DomainMetrics] = defaultdict(_DomainMetrics)
        self._start_time = time.time()
        self._total_requests = 0
        self._total_latencies: List[float] = []

    # Return the metrics bucket for a domain.
    def _dm(self, domain: str) -> _DomainMetrics:
        return self._domains[domain]

    # Record one HTTP request result.
    def record_request(
        self,
        domain: str,
        status: int,
        latency: float,
        bytes_: int = 0,
    ):
        """Record one HTTP request outcome."""

        domain_metrics = self._dm(domain)
        domain_metrics.requests += 1
        domain_metrics.latencies.append(latency)
        domain_metrics.total_bytes += bytes_
        self._total_requests += 1
        self._total_latencies.append(latency)

        if 200 <= status < 300:
            domain_metrics.success += 1
        elif status == 429:
            domain_metrics.blocked_429 += 1
            logger.warning(f"429 rate-limited: {domain}")
        elif status == 403:
            domain_metrics.blocked_403 += 1
            logger.warning(f"403 blocked: {domain}")
        elif 500 <= status < 600:
            domain_metrics.errors_5xx += 1
        else:
            domain_metrics.failed += 1

    # Record one parse result.
    def record_parse(self, domain: str, success: bool):
        """Record a parser success or failure for a domain."""

        domain_metrics = self._dm(domain)
        if success:
            domain_metrics.parse_success += 1
        else:
            domain_metrics.parse_failed += 1

    # Record one cache result.
    def record_cache(self, domain: str, hit: bool):
        """Record a cache hit or miss for a domain."""

        domain_metrics = self._dm(domain)
        if hit:
            domain_metrics.cache_hits += 1
        else:
            domain_metrics.cache_misses += 1

    # Record one retry event.
    def record_retry(self, domain: str):
        """Record a retry event for a domain."""

        self._dm(domain).retries += 1

    # Compute a percentile over numeric values.
    def _percentile(self, data: List[float], percentile: float) -> float:
        """Compute a percentile from a list of latencies."""

        if not data:
            return 0.0
        sorted_data = sorted(data)
        index = (len(sorted_data) - 1) * percentile / 100.0
        floor_index, ceil_index = int(index), int(index) + 1
        if ceil_index >= len(sorted_data):
            return sorted_data[-1]
        return sorted_data[floor_index] + (index - floor_index) * (
            sorted_data[ceil_index] - sorted_data[floor_index]
        )

    # Build the structured metrics summary.
    def summary(self) -> Dict:
        """Build a structured metrics report for the current run."""

        elapsed = time.time() - self._start_time
        total = max(self._total_requests, 1)

        total_429 = sum(metrics.blocked_429 for metrics in self._domains.values())
        total_403 = sum(metrics.blocked_403 for metrics in self._domains.values())
        total_success = sum(metrics.success for metrics in self._domains.values())
        total_cache_hits = sum(metrics.cache_hits for metrics in self._domains.values())
        total_cache_total = sum(metrics.cache_hits + metrics.cache_misses for metrics in self._domains.values())
        total_parse_ok = sum(metrics.parse_success for metrics in self._domains.values())
        total_parse_total = sum(metrics.parse_success + metrics.parse_failed for metrics in self._domains.values())
        total_bytes = sum(metrics.total_bytes for metrics in self._domains.values())
        total_retries = sum(metrics.retries for metrics in self._domains.values())

        report = {
            "elapsed_sec": round(elapsed, 1),
            "total_requests": self._total_requests,
            "block_rate_429": round(total_429 / total, 3),
            "block_rate_403": round(total_403 / total, 3),
            "success_rate": round(total_success / total, 3),
            "cache_hit_rate": round(total_cache_hits / max(total_cache_total, 1), 3),
            "latency": {
                "avg": round(sum(self._total_latencies) / max(len(self._total_latencies), 1), 3),
                "p50": round(self._percentile(self._total_latencies, 50), 3),
                "p95": round(self._percentile(self._total_latencies, 95), 3),
                "p99": round(self._percentile(self._total_latencies, 99), 3),
            },
            "parse_success_rate": round(total_parse_ok / max(total_parse_total, 1), 3),
            "total_bytes_mb": round(total_bytes / (1024 * 1024), 2),
            "retry_rate": round(total_retries / total, 3),
            "domains": {},
        }

        for domain, metrics in self._domains.items():
            report["domains"][domain] = {
                "requests": metrics.requests,
                "success": metrics.success,
                "blocked_429": metrics.blocked_429,
                "blocked_403": metrics.blocked_403,
                "errors_5xx": metrics.errors_5xx,
                "cache_hits": metrics.cache_hits,
                "retries": metrics.retries,
                "parse_success": metrics.parse_success,
                "parse_failed": metrics.parse_failed,
                "latency_avg": round(sum(metrics.latencies) / max(len(metrics.latencies), 1), 3),
                "bytes_mb": round(metrics.total_bytes / (1024 * 1024), 2),
            }

        return report

    # Build a text report for logs.
    def format_report(self) -> str:
        """Build a human-readable metrics report."""

        summary = self.summary()
        lines = [
            "+------------------------------------------+",
            "| CRAWL METRICS REPORT                    |",
            "+------------------------------------------+",
            f"| Time elapsed : {summary['elapsed_sec']:.0f}s",
            f"| Requests     : {summary['total_requests']}",
            f"| Success rate : {summary['success_rate']:.1%}",
            f"| Block 429    : {summary['block_rate_429']:.1%}",
            f"| Block 403    : {summary['block_rate_403']:.1%}",
            f"| Cache hit    : {summary['cache_hit_rate']:.1%}",
            f"| Parse OK     : {summary['parse_success_rate']:.1%}",
            f"| Retry rate   : {summary['retry_rate']:.1%}",
            f"| Traffic      : {summary['total_bytes_mb']:.1f} MB",
            f"| Latency avg  : {summary['latency']['avg']:.3f}s",
            f"| Latency p95  : {summary['latency']['p95']:.3f}s",
            f"| Latency p99  : {summary['latency']['p99']:.3f}s",
            "+------------------------------------------+",
        ]
        for domain, metrics in summary.get("domains", {}).items():
            lines.append(
                f"| {domain[:30]:30s} "
                f"req={metrics['requests']:3d} "
                f"ok={metrics['success']:3d} "
                f"429={metrics['blocked_429']:2d} "
                f"403={metrics['blocked_403']:2d} "
                f"cache={metrics['cache_hits']:2d}"
            )
        lines.append("+------------------------------------------+")
        return "\n".join(lines)

    # Write the structured summary to logs.
    def log_summary(self):
        """Write the metrics summary to structured logs."""

        summary = self.summary()
        logger.info(
            "Crawl metrics summary",
            extra={
                "crawl_metrics": summary,
                "total_requests": summary["total_requests"],
                "success_rate": summary["success_rate"],
                "block_rate_429": summary["block_rate_429"],
                "block_rate_403": summary["block_rate_403"],
                "cache_hit_rate": summary["cache_hit_rate"],
            },
        )

    # Request context manager.
    class RequestTracker:
        """Track one request inside a context manager."""

        # Store request state while the context is open.
        def __init__(self, metrics: "CrawlMetrics", domain: str):
            self._metrics = metrics
            self._domain = domain
            self._start = 0.0
            self._status = 0
            self._bytes = 0

        # Set the final HTTP status code.
        def set_status(self, status: int):
            self._status = status

        # Set the transferred byte count.
        def set_bytes(self, n: int):
            self._bytes = n

        # Enter the timing context.
        def __enter__(self):
            self._start = time.time()
            return self

        # Exit the timing context and record the request.
        def __exit__(self, exc_type, exc_val, exc_tb):
            latency = time.time() - self._start
            if exc_type is not None:
                self._status = self._status or 0
            if self._status > 0:
                self._metrics.record_request(
                    self._domain,
                    status=self._status,
                    latency=latency,
                    bytes_=self._bytes,
                )
            return False

    # Build a request-tracking context manager.
    def track_request(self, domain: str) -> "CrawlMetrics.RequestTracker":
        """Return a request-tracking context manager."""

        return self.RequestTracker(self, domain)

"""
Performance monitoring for tracking response latencies and sending alerts.
"""

from typing import Dict, Optional
from collections import deque
import statistics
import slack_bot.alerting


class PerformanceMonitor:
    """Monitor and track response latencies with alerting."""

    def __init__(
        self,
        slow_threshold_seconds: float = 30.0,
        max_history_size: int = 1000,
        slack_client=None,
        alert_channel: Optional[str] = None,
    ):
        """
        Initialize performance monitor.

        Args:
            slow_threshold_seconds: Threshold for slow response alerts (default 30s)
            max_history_size: Maximum number of latencies to keep in history
            slack_client: Optional Slack client for alerts
            alert_channel: Optional Slack channel ID for alerts
        """
        self.slow_threshold = slow_threshold_seconds
        self.slack_client = slack_client
        self.alert_channel = alert_channel
        self.latencies: deque = deque(maxlen=max_history_size)
        self.request_log: Dict = {}

    def record_response_time(
        self,
        request_id: str,
        duration_seconds: float,
        user_id: Optional[str] = None,
        channel_id: Optional[str] = None,
    ) -> None:
        """
        Record a response time measurement.

        Args:
            request_id: Unique request identifier
            duration_seconds: Response duration in seconds
            user_id: Optional Slack user ID
            channel_id: Optional Slack channel ID
        """
        # Store latency
        self.latencies.append(duration_seconds)

        # Store request details
        self.request_log[request_id] = {
            "duration": duration_seconds,
            "user_id": user_id,
            "channel_id": channel_id,
        }

        # Check if slow threshold exceeded
        if duration_seconds > self.slow_threshold:
            self._send_slow_alert(request_id, duration_seconds, user_id, channel_id)

    def _send_slow_alert(
        self,
        request_id: str,
        duration_seconds: float,
        user_id: Optional[str] = None,
        channel_id: Optional[str] = None,
    ) -> None:
        """Send alert for slow responses."""
        title = "Slow Response Detected"
        message = (
            f"Request {request_id} took {duration_seconds:.2f}s "
            f"(threshold: {self.slow_threshold}s)"
        )

        # Pass as positional arguments so mocks can capture them
        slack_bot.alerting.send_performance_alert(
            title,
            message,
            slack_client=self.slack_client,
            channel_id=self.alert_channel or channel_id,
        )

    def get_average_latency(self) -> Optional[float]:
        """
        Get average latency from recorded measurements.

        Returns:
            Average latency in seconds, or None if no measurements
        """
        if not self.latencies:
            return None
        return statistics.mean(self.latencies)

    def get_p95_latency(self) -> Optional[float]:
        """
        Get 95th percentile latency.

        Returns:
            P95 latency in seconds, or None if insufficient data
        """
        if len(self.latencies) < 20:
            # Need at least 20 measurements for meaningful percentile
            return None

        sorted_latencies = sorted(self.latencies)
        # Calculate 95th percentile index
        index = int(len(sorted_latencies) * 0.95)
        if index >= len(sorted_latencies):
            index = len(sorted_latencies) - 1

        return sorted_latencies[index]

    def get_latency_histogram(self) -> Dict:
        """
        Get latency histogram data.

        Returns:
            Dictionary with histogram data
        """
        if not self.latencies:
            return {"buckets": []}

        # Create histogram buckets (0-1s, 1-2s, 2-5s, 5-10s, 10s+)
        buckets = {
            "0-1s": 0,
            "1-2s": 0,
            "2-5s": 0,
            "5-10s": 0,
            "10s+": 0,
        }

        for latency in self.latencies:
            if latency < 1:
                buckets["0-1s"] += 1
            elif latency < 2:
                buckets["1-2s"] += 1
            elif latency < 5:
                buckets["2-5s"] += 1
            elif latency < 10:
                buckets["5-10s"] += 1
            else:
                buckets["10s+"] += 1

        return {"buckets": buckets}

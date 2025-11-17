"""Metrics publishing utilities for Home Assistant integrations."""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

from .config import BotConfig, HomeAssistantSettings
from .paths import DATA_DIR

ErrorHandler = Optional[Callable[[str], None]]


class MetricsPublisher:
    """Persist metrics to disk and optionally mirror them to MQTT."""

    def __init__(self, config: BotConfig, on_error: ErrorHandler = None) -> None:
        self._ha: HomeAssistantSettings = config.home_assistant
        self._metrics_path = DATA_DIR / self._ha.rest_api.metrics_file
        self._metrics_path.parent.mkdir(parents=True, exist_ok=True)
        self._on_error = on_error
        self._mqtt_client = None
        self._mqtt_connected = False

        if self._ha.mqtt.enabled:
            try:
                import paho.mqtt.client as mqtt  # type: ignore
            except Exception as exc:  # pragma: no cover - optional dependency
                self._report_error(f"MQTT disabled: {exc}")
            else:
                try:
                    client = mqtt.Client()
                    if self._ha.mqtt.username:
                        client.username_pw_set(self._ha.mqtt.username, self._ha.mqtt.password or None)
                    client.connect(self._ha.mqtt.host, int(self._ha.mqtt.port), keepalive=60)
                    client.loop_start()
                except Exception as exc:  # pragma: no cover - network edge cases
                    self._report_error(f"MQTT connection failed: {exc}")
                else:
                    self._mqtt_client = client
                    self._mqtt_connected = True

    def _report_error(self, message: str) -> None:
        if self._on_error:
            self._on_error(message)

    def publish(self, payload: Dict[str, Any]) -> None:
        try:
            tmp = self._metrics_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._metrics_path)
        except Exception as exc:  # pragma: no cover - disk edge cases
            self._report_error(f"Failed to write metrics file: {exc}")

        if self._mqtt_client and self._mqtt_connected:
            base = self._ha.mqtt.base_topic.rstrip("/") or "bithumb_bot"
            for key, value in payload.items():
                if isinstance(value, (dict, list)):
                    body = json.dumps(value, ensure_ascii=False)
                else:
                    body = str(value)
                try:
                    self._mqtt_client.publish(f"{base}/{key}", body, qos=0, retain=True)
                except Exception as exc:  # pragma: no cover - network edge cases
                    self._report_error(f"Failed to publish MQTT topic {key}: {exc}")

    def close(self) -> None:
        if self._mqtt_client and self._mqtt_connected:
            try:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
            except Exception:  # pragma: no cover - defensive
                pass
            finally:
                self._mqtt_connected = False
                self._mqtt_client = None


__all__ = ["MetricsPublisher", "DATA_DIR"]

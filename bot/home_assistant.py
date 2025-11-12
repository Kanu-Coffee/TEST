"""Helpers for Home Assistant integrations (MQTT + metrics file)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .config import BotConfig

ErrorHandler = Optional[Callable[[str], None]]


class HomeAssistantPublisher:
    """Publish bot metrics to MQTT and persist them for HTTP gateways."""

    def __init__(self, config: BotConfig, data_dir: Path, on_error: ErrorHandler = None) -> None:
        self._config = config.home_assistant
        self._metrics_path = data_dir / self._config.metrics_file
        self._metrics_path.parent.mkdir(parents=True, exist_ok=True)
        self._on_error = on_error
        self._mqtt_client = None
        self._mqtt_connected = False

        if self._config.mqtt.enabled:
            try:
                import paho.mqtt.client as mqtt  # type: ignore
            except Exception as exc:  # pragma: no cover - optional dependency
                self._report_error(f"MQTT disabled: {exc}")
            else:
                try:
                    self._mqtt_client = mqtt.Client()
                    if self._config.mqtt.username:
                        self._mqtt_client.username_pw_set(
                            self._config.mqtt.username, self._config.mqtt.password or None
                        )
                    self._mqtt_client.connect(
                        self._config.mqtt.host,
                        int(self._config.mqtt.port),
                        keepalive=60,
                    )
                    self._mqtt_client.loop_start()
                    self._mqtt_connected = True
                except Exception as exc:  # pragma: no cover - network edge cases
                    self._report_error(f"MQTT connection failed: {exc}")
                    self._mqtt_client = None
                    self._mqtt_connected = False

    def _report_error(self, message: str) -> None:
        if self._on_error:
            self._on_error(message)

    def publish(self, payload: Dict[str, Any]) -> None:
        """Write payload to disk and publish values to MQTT topics."""

        try:
            tmp_path = self._metrics_path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            tmp_path.replace(self._metrics_path)
        except Exception as exc:  # pragma: no cover - disk issues
            self._report_error(f"Failed to write metrics file: {exc}")

        if self._mqtt_client and self._mqtt_connected:
            base = self._config.mqtt.base_topic.rstrip("/")
            for key, value in payload.items():
                topic = f"{base}/{key}"
                if isinstance(value, (dict, list)):
                    body = json.dumps(value, ensure_ascii=False)
                else:
                    body = str(value)
                try:
                    self._mqtt_client.publish(topic, body, qos=0, retain=True)
                except Exception as exc:  # pragma: no cover - network edge cases
                    self._report_error(f"Failed to publish MQTT topic {topic}: {exc}")

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

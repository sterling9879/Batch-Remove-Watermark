"""Utilities for interacting with the WaveSpeed video watermark removal API."""
from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass
from typing import Dict, Optional

import requests


DEFAULT_API_BASE = "https://api.wavespeed.ai/api/v3"


class WaveSpeedError(RuntimeError):
    """Represents an error returned by the WaveSpeed API."""


@dataclass
class WaveSpeedResult:
    request_id: str
    status: str
    result_url: Optional[str] = None
    raw_response: Optional[Dict] = None


class WaveSpeedWatermarkRemover:
    """Client responsible for sending videos to the WaveSpeed API."""

    def __init__(
        self,
        api_key: str,
        *,
        api_base: str = DEFAULT_API_BASE,
        poll_interval: float = 5.0,
        poll_timeout: float = 600.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        if not api_key:
            raise ValueError("An API key is required to use the WaveSpeed client.")
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self.session = session or requests.Session()

    # ---- public API -----------------------------------------------------
    def process_video(self, file_path: str, *, filename: Optional[str] = None) -> WaveSpeedResult:
        """Send a video for watermark removal and wait for the result."""

        upload_url = self._upload_video(file_path, filename=filename)
        request_id = self._create_prediction(upload_url)
        return self._poll_for_result(request_id)

    # ---- HTTP helpers ---------------------------------------------------
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
        }

    def _upload_video(self, file_path: str, *, filename: Optional[str] = None) -> str:
        """Upload the local file and return a public URL usable by WaveSpeed."""

        filename = filename or os.path.basename(file_path)
        with open(file_path, "rb") as file_handle:
            files = {
                "file": (filename, file_handle, "application/octet-stream"),
            }
            response = self.session.post(
                f"{self.api_base}/uploads",
                headers=self._headers(),
                files=files,
                timeout=60,
            )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:  # pragma: no cover - thin wrapper
            raise WaveSpeedError(f"Upload failed: {exc}") from exc
        data = response.json()
        upload_url = data.get("url") or data.get("file_url")
        if not upload_url:
            raise WaveSpeedError("Unexpected upload response structure; expected a URL.")
        return upload_url

    def _create_prediction(self, video_url: str) -> str:
        payload = {"video": video_url}
        headers = {**self._headers(), "Content-Type": "application/json"}
        response = self.session.post(
            f"{self.api_base}/wavespeed-ai/video-watermark-remover",
            headers=headers,
            json=payload,
            timeout=30,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:  # pragma: no cover - thin wrapper
            raise WaveSpeedError(f"Prediction creation failed: {exc}") from exc
        data = response.json()
        request_id = (
            data.get("request_id")
            or data.get("requestId")
            or data.get("id")
            or data.get("prediction_id")
        )
        if not request_id:
            raise WaveSpeedError("Prediction response did not include a request ID.")
        return request_id

    def _poll_for_result(self, request_id: str) -> WaveSpeedResult:
        start_time = time.time()
        while True:
            response = self.session.get(
                f"{self.api_base}/predictions/{request_id}/result",
                headers=self._headers(),
                timeout=30,
            )
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:  # pragma: no cover - thin wrapper
                raise WaveSpeedError(f"Polling failed: {exc}") from exc
            data = response.json()
            status = data.get("status") or data.get("state") or data.get("result", {}).get("status")
            if status in {"succeeded", "failed", "error"}:
                result_url = self._extract_result_url(data)
                return WaveSpeedResult(
                    request_id=request_id,
                    status=status,
                    result_url=result_url,
                    raw_response=data,
                )
            if time.time() - start_time > self.poll_timeout:
                raise WaveSpeedError(
                    f"Timed out after {self.poll_timeout} seconds waiting for result of {request_id}."
                )
            time.sleep(self.poll_interval)

    # ---- utilities ------------------------------------------------------
    @staticmethod
    def _extract_result_url(data: Dict) -> Optional[str]:
        if "result" not in data:
            return None
        result_payload = data["result"]
        if isinstance(result_payload, str):
            return result_payload
        if isinstance(result_payload, dict):
            # try common keys
            for key in ("video", "output", "url", "video_url"):
                value = result_payload.get(key)
                if isinstance(value, str):
                    return value
            # handle nested structures
            for value in result_payload.values():
                if isinstance(value, str) and value.startswith("http"):
                    return value
        return None


def encode_file_to_base64(path: str) -> str:
    """Utility helper: encode a file into base64 for debugging."""

    with open(path, "rb") as file_handle:
        return base64.b64encode(file_handle.read()).decode("utf-8")

import logging
import random
import time
from urllib.parse import urlparse, urlunparse

import requests

from app.config import (
    BACKOFF_JITTER_SECONDS,
    BACKOFF_SECONDS,
    MAX_RETRIES,
    REQUEST_CONNECT_TIMEOUT_SECONDS,
    REQUEST_DELAY_SECONDS,
    REQUEST_READ_TIMEOUT_SECONDS,
)


logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

DNS_ERROR_MARKERS = (
    "nameresolutionerror",
    "failed to resolve",
    "temporary failure in name resolution",
    "no address associated with hostname",
)


class HttpRequestError(Exception):
    def __init__(
        self,
        message: str,
        *,
        url: str,
        status_code: int | None = None,
        retryable: bool = False,
        error_kind: str | None = None,
    ) -> None:
        super().__init__(message)
        self.url = url
        self.status_code = status_code
        self.retryable = retryable
        self.error_kind = error_kind


def _is_dns_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in DNS_ERROR_MARKERS)


def _build_fallback_url(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc
    if not host:
        return None

    host_lower = host.lower()
    if "carsensor.net" not in host_lower:
        return None

    if host_lower.startswith("www."):
        new_host = host[4:]
    else:
        new_host = f"www.{host}"

    if new_host.lower() == host_lower:
        return None

    swapped = parsed._replace(netloc=new_host)
    return urlunparse(swapped)


class HttpClient:
    def __init__(self) -> None:
        self._session = requests.Session()

    def get(self, url: str, *, allow_404: bool = False) -> requests.Response:
        try:
            return self._request_with_retries(url, allow_404=allow_404)
        except HttpRequestError as exc:
            if exc.error_kind != "dns":
                raise

            fallback_url = _build_fallback_url(url)
            if not fallback_url:
                raise

            logger.warning("DNS resolution issue for %s. Retrying with fallback host: %s", url, fallback_url)
            return self._request_with_retries(fallback_url, allow_404=allow_404)

    def _request_with_retries(self, url: str, *, allow_404: bool) -> requests.Response:
        last_error: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self._session.get(
                    url,
                    headers=DEFAULT_HEADERS,
                    timeout=(REQUEST_CONNECT_TIMEOUT_SECONDS, REQUEST_READ_TIMEOUT_SECONDS),
                    allow_redirects=True,
                )

                if response.status_code == 404 and allow_404:
                    return response

                if response.status_code >= 500:
                    raise HttpRequestError(
                        f"HTTP {response.status_code}",
                        url=url,
                        status_code=response.status_code,
                        retryable=True,
                        error_kind="http_5xx",
                    )

                if response.status_code >= 400:
                    raise HttpRequestError(
                        f"HTTP {response.status_code}",
                        url=url,
                        status_code=response.status_code,
                        retryable=False,
                        error_kind="http_4xx",
                    )

                response.raise_for_status()
                current_encoding = (response.encoding or "").lower()
                if response.apparent_encoding and current_encoding in {"", "iso-8859-1", "latin-1", "cp1252"}:
                    response.encoding = response.apparent_encoding

                if REQUEST_DELAY_SECONDS > 0:
                    time.sleep(REQUEST_DELAY_SECONDS)

                return response

            except HttpRequestError as exc:
                last_error = exc
                if not exc.retryable or attempt >= MAX_RETRIES:
                    break
                self._sleep_retry(url, attempt, exc)
            except requests.Timeout as exc:
                wrapped = HttpRequestError(
                    str(exc),
                    url=url,
                    status_code=None,
                    retryable=True,
                    error_kind="timeout",
                )
                last_error = wrapped
                if attempt >= MAX_RETRIES:
                    break
                self._sleep_retry(url, attempt, wrapped)
            except requests.ConnectionError as exc:
                is_dns = _is_dns_error(exc)
                wrapped = HttpRequestError(
                    str(exc),
                    url=url,
                    status_code=None,
                    retryable=not is_dns,
                    error_kind="dns" if is_dns else "connection",
                )
                last_error = wrapped
                if is_dns or attempt >= MAX_RETRIES:
                    break
                self._sleep_retry(url, attempt, wrapped)

        if isinstance(last_error, HttpRequestError):
            raise last_error
        if last_error is None:
            raise HttpRequestError("Unknown HTTP error", url=url, retryable=False)
        raise HttpRequestError(str(last_error), url=url, retryable=False)

    def _sleep_retry(self, url: str, attempt: int, exc: Exception) -> None:
        sleep_seconds = (BACKOFF_SECONDS * (2 ** (attempt - 1))) + random.uniform(0.0, BACKOFF_JITTER_SECONDS)
        logger.warning(
            "Request failed (%s/%s) for %s: %s. Retrying in %.2fs",
            attempt,
            MAX_RETRIES,
            url,
            exc,
            sleep_seconds,
        )
        time.sleep(sleep_seconds)

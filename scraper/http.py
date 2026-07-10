from __future__ import annotations

import time
from typing import Callable

import requests
from requests import RequestException
from requests.adapters import HTTPAdapter
from urllib3.util import Retry


class HttpClient:
    def __init__(
        self,
        timeout: float = 20,
        delay: float = 1,
        retries: int = 3,
        backoff: float = 1,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.timeout = timeout
        self.delay = delay
        self.retries = retries
        self.backoff = backoff
        self.session = session or requests.Session()
        self.session.headers.update(
            {"User-Agent": "native-plant-finder/1.0 (sequential research scraper)"}
        )
        retry_policy = Retry(
            total=max(retries - 1, 0),
            connect=max(retries - 1, 0),
            read=max(retries - 1, 0),
            status=max(retries - 1, 0),
            backoff_factor=backoff,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "POST"}),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry_policy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.sleep = sleep
        self._made_request = False
        self._attempts = 0

    @property
    def attempts(self) -> int:
        return self._attempts

    def reset_attempts(self) -> None:
        self._attempts = 0

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        if self._made_request and self.delay:
            self.sleep(self.delay)
        self._made_request = True
        self._attempts += 1
        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        except RequestException:
            self._attempts += max(self.retries - 1, 0)
            raise
        retries = getattr(getattr(response, "raw", None), "retries", None)
        self._attempts += len(getattr(retries, "history", ()))
        response.raise_for_status()
        return response

    def get(self, url: str, **kwargs) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        return self.request("POST", url, **kwargs)

"""HTTP client."""

import logging
from typing import Any

import primp

from .exceptions import DDGSException, TimeoutException

logger = logging.getLogger(__name__)


class Response:
    """HTTP response."""

    __slots__ = ("status_code", "text")

    def __init__(self, resp: Any) -> None:  # noqa: ANN401
        self.status_code = resp.status_code
        self.text = resp.text


class HttpClient:
    """HTTP client."""

    def __init__(
        self,
        proxy: str | None = None,
        timeout: int | None = 10,
        *,
        verify: bool | str = True,
        impersonate: str = "random",
        impersonate_os: str = "random",
    ) -> None:
        """Initialize the HttpClient object.

        Args:
            proxy (str, optional): proxy for the HTTP client, supports http/https/socks5 protocols.
                example: "http://user:pass@example.com:3128". Defaults to None.
            timeout (int, optional): Timeout value for the HTTP client. Defaults to 10.
            verify: (bool | str):  True to verify, False to skip, or a str path to a PEM file. Defaults to True.
            impersonate: primp browser profile (e.g. chrome124).
            impersonate_os: primp OS profile (e.g. windows).

        """
        self.client = primp.Client(
            proxy=proxy,
            timeout=timeout,
            impersonate=impersonate,
            impersonate_os=impersonate_os,
            verify=verify if isinstance(verify, bool) else True,
            ca_cert_file=verify if isinstance(verify, str) else None,
        )

    def request(self, *args: Any, **kwargs: Any) -> Response:  # noqa: ANN401
        """Make a request to the HTTP client."""
        try:
            resp = self.client.request(*args, **kwargs)
            return Response(resp)
        except primp.TimeoutError as ex:
            raise TimeoutException(ex) from ex
        except Exception as ex:
            msg = f"{type(ex).__name__}: {ex!r}"
            raise DDGSException(msg) from ex

    def get(self, url: str, *args: Any, **kwargs: Any) -> Response:  # noqa: ANN401
        """Make a GET request to the HTTP client."""
        return self.request("GET", url, *args, **kwargs)

    def post(self, url: str, *args: Any, **kwargs: Any) -> Response:  # noqa: ANN401
        """Make a POST request to the HTTP client."""
        return self.request("POST", url, *args, **kwargs)

import httpx
from fastapi import HTTPException, Response, status

TIMEOUT_SECONDS = 10.0
RELAYED_HEADERS = ("content-type", "x-content-type-options")


class Upstream:
    def __init__(self, name, base_url, transport=None):
        self._name = name
        self._client = httpx.Client(
            base_url=base_url,
            timeout=TIMEOUT_SECONDS,
            follow_redirects=False,
            transport=transport,
        )

    def request(self, method, path, token, *, params=None, content=None, content_type=None):
        headers = {"Authorization": f"Bearer {token}"}
        if content_type is not None:
            headers["Content-Type"] = content_type
        try:
            return self._client.request(method, path, params=params, content=content, headers=headers)
        except httpx.TimeoutException:
            raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, f"{self._name} timed out")
        except httpx.HTTPError:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{self._name} unavailable")


def relay(response):
    if response.status_code == status.HTTP_401_UNAUTHORIZED or response.status_code >= 500:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Upstream error")
    headers = {k: v for k, v in response.headers.items() if k.lower() in RELAYED_HEADERS}
    return Response(content=response.content, status_code=response.status_code, headers=headers)

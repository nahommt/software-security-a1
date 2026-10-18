import httpx
from fastapi import HTTPException, status

TIMEOUT_SECONDS = 5.0


class CarServiceClient:
    def __init__(self, base_url, transport=None):
        self._base_url = base_url
        self._transport = transport

    def _client(self, job_token):
        return httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {job_token}"},
            timeout=TIMEOUT_SECONDS,
            follow_redirects=False,
            transport=self._transport,
        )

    def _send(self, client, method, path, **kwargs):
        try:
            response = client.request(method, path, **kwargs)
        except httpx.TimeoutException:
            raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "car-service timed out")
        except httpx.HTTPError:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "car-service unavailable")
        if response.status_code == status.HTTP_404_NOT_FOUND:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        if response.status_code == status.HTTP_409_CONFLICT:
            raise HTTPException(status.HTTP_409_CONFLICT, "Report for this job already exists")
        if response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
        if not response.is_success:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "car-service error")
        return response.json()

    def run_job(self, job_token, car_id, build_report):
        with self._client(job_token) as client:
            car = self._send(client, "GET", f"/cars/{car_id}")
            valuations = self._send(client, "GET", f"/cars/{car_id}/valuations")
            content = build_report(car, valuations)
            return self._send(client, "POST", f"/cars/{car_id}/reports", json={"content": content})

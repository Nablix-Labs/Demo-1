"""Shared HTTP helper for adapters that call live downstream services.

Adapters still own their DTO-specific parsing and error naming. This module
only handles the common mechanics: POST JSON, retry transient transport or
server errors, require an object JSON response, and raise `AdapterError` with
request/response context when the call cannot be trusted.
"""

from typing import cast

import httpx

from app.core.exceptions import AdapterError
from app.core.logger import logger


JsonObject = dict[str, object]


async def post_json(
    adapter_name: str,
    url: str,
    payload: JsonObject,
    timeout_seconds: int,
    retry_count: int,
) -> JsonObject:
    """POST JSON with bounded retries and return the parsed JSON object."""

    max_attempts: int = retry_count + 1
    for attempt in range(1, max_attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as http_client:
                response: httpx.Response = await http_client.post(url, json=payload)
        except httpx.HTTPError as error:
            if attempt < max_attempts:
                logger.warning(
                    "adapter_request_retry",
                    extra={
                        "adapter_name": adapter_name,
                        "url": url,
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                    },
                )
                continue
            raise AdapterError(
                adapter_name,
                f"request failed url={url} payload={payload}: {error}",
            ) from error

        if response.status_code >= 400:
            if attempt < max_attempts:
                logger.warning(
                    "adapter_response_retry",
                    extra={
                        "adapter_name": adapter_name,
                        "url": url,
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "status_code": response.status_code,
                        "response_body": response.text,
                    },
                )
                continue
            raise AdapterError(
                adapter_name,
                f"url={url} status={response.status_code} body={response.text} payload={payload}",
            )

        try:
            body: object = response.json()
        except ValueError as error:
            raise AdapterError(
                adapter_name,
                f"invalid JSON response url={url} status={response.status_code} body={response.text}",
            ) from error

        if not isinstance(body, dict):
            raise AdapterError(
                adapter_name,
                f"response JSON must be an object url={url} status={response.status_code} body={body}",
            )
        return cast(JsonObject, body)

    raise AdapterError(adapter_name, f"request exhausted retries url={url} payload={payload}")

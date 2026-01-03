"""REST client handling, including PlanetScaleAPIStream base class.

Copyright (c) 2025 Edgar Ramírez-Mondragón
"""

from __future__ import annotations

import abc
from importlib import resources
from typing import TYPE_CHECKING, Any, NamedTuple, cast, override

from singer_sdk import OpenAPISchema, StreamSchema
from singer_sdk.authenticators import APIKeyAuthenticator
from singer_sdk.pagination import BasePageNumberPaginator
from singer_sdk.streams import RESTStream
from toolz.dicttoolz import get_in

from tap_planetscaleapi import openapi

if TYPE_CHECKING:
    from singer_sdk import Stream
    from singer_sdk.helpers.types import Context


class StreamKey(NamedTuple):
    """A key for a stream in the OpenAPI spec."""

    path: str
    method: str
    expected_status: int = 200


class PlanetScaleOpenAPISource(OpenAPISchema[StreamKey]):
    """OpenAPI source for PlanetScale API."""

    @override
    def get_unresolved_schema(self, key: StreamKey) -> dict[str, Any]:
        return get_in(  # type: ignore[no-any-return,no-untyped-call]
            [
                "paths",
                key.path,
                key.method,
                "responses",
                str(key.expected_status),
                "schema",
            ],
            self.spec,
        )

    @override
    def fetch_schema(self, key: StreamKey) -> dict[str, Any]:
        from tap_planetscaleapi import streams  # noqa: PLC0415

        schema = super().fetch_schema(key)["properties"]["data"]["items"]
        if key.path == streams.BackupsStream.spec_path:
            schema["properties"]["deleted_at"]["type"] = ["string", "null"]
        return schema  # type: ignore[no-any-return]


class SchemaFromPath(StreamSchema[StreamKey]):
    """A stream schema from a path in the OpenAPI spec."""

    @override
    def get_stream_schema(
        self,
        stream: Stream,
        stream_class: type[Stream],
    ) -> dict[str, Any]:
        stream = cast("PlanetScaleAPIStream", stream)
        key = StreamKey(
            path=stream.spec_path or stream.path,
            method=stream.http_method.lower(),
            expected_status=200,
        )
        return self.schema_source.get_schema(key)


class PlanetScaleAPIStream(RESTStream[int], abc.ABC):
    """PlanetScaleAPI stream class."""

    # Class properties
    PAGE_SIZE = 100
    records_jsonpath = "$.data[*]"

    #: The endpoint for this resource in the OpenAPI spec. If not provided, the
    #: `path` attribute is used.
    spec_path: str | None = None

    schema = SchemaFromPath(PlanetScaleOpenAPISource(resources.files(openapi) / "openapi.json"))

    @property
    @override
    def url_base(self) -> str:
        return "https://api.planetscale.com/v1"

    @property
    @override
    def authenticator(self) -> APIKeyAuthenticator:
        token_id = self.config["service_token_id"]
        token = self.config["service_token"]
        return APIKeyAuthenticator(key="Authorization", value=f"{token_id}:{token}", location="header")

    @property
    @override
    def http_headers(self) -> dict[str, str]:
        return {
            "accept": "application/json",
            "user-agent": self.user_agent,
        }

    @override
    def get_new_paginator(self) -> BasePageNumberPaginator:
        return BasePageNumberPaginator(1)

    @override
    def get_url_params(self, context: Context | None, next_page_token: Any | None) -> dict[str, Any]:
        params: dict[str, Any] = {"per_page": self.PAGE_SIZE}
        if next_page_token:
            params["page"] = next_page_token

        return params

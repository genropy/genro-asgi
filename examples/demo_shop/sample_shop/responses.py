"""TypedDict response types for API documentation.

These types provide schema information for OpenAPI documentation.
When genro-routes supports TypedDict introspection, these will be
automatically converted to OpenAPI response schemas.
"""

from typing import Any, TypedDict


class SuccessResponse(TypedDict):
    """Base success response."""
    success: bool


class ErrorResponse(TypedDict):
    """Error response."""
    success: bool
    error: str


class IdResponse(TypedDict):
    """Response with id and message (for add/create operations)."""
    success: bool
    id: int
    message: str


class MessageResponse(TypedDict):
    """Response with just a message (for delete/update operations)."""
    success: bool
    message: str


class RecordResponse(TypedDict):
    """Response with a single record (for get operations)."""
    success: bool
    record: dict[str, Any]


class ListResponse(TypedDict):
    """Response with a list of records (for list operations)."""
    success: bool
    count: int
    records: list[dict[str, Any]]


class StatsResponse(TypedDict):
    """Statistics response (for analytics operations)."""
    success: bool
    total_purchases: int
    total_revenue: float
    top_articles: list[dict[str, Any]]


__all__ = [
    "SuccessResponse",
    "ErrorResponse",
    "IdResponse",
    "MessageResponse",
    "RecordResponse",
    "ListResponse",
    "StatsResponse",
]

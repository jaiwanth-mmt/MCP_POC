import httpx

from models.models import SearchAPIResponse, HoldAPIResponse
from services.logging_config import get_logger

logger = get_logger(__name__, service="api_client")

SEARCH_API_URL = "http://10.212.94.147:1077/cabs/mcp/search"
HOLD_API_URL = "http://10.212.94.147:1072/cabs/mcp/hold"

API_TIMEOUT = 30.0


async def search_cabs(payload: dict) -> SearchAPIResponse:
    """POST to the Search API and return a parsed SearchAPIResponse."""
    logger.info(
        "Calling Search API",
        extra={"url": SEARCH_API_URL, "pickupTime": payload.get("pickupTime")}
    )

    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            response = await client.post(
                SEARCH_API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

        result = SearchAPIResponse(**data)
        logger.info(
            "Search API response received",
            extra={
                "searchId": result.searchId,
                "cab_count": len(result.cabs),
                "distance_km": result.totalDistanceInKm,
                "duration_min": result.totalApproxDurationInMin,
            }
        )
        return result

    except httpx.TimeoutException:
        logger.error("Search API request timed out", extra={"url": SEARCH_API_URL})
        raise ValueError(
            "The cab search service is taking too long to respond. "
            "Please try again in a moment."
        )
    except httpx.HTTPStatusError as e:
        logger.error(
            "Search API returned error status",
            extra={"status_code": e.response.status_code, "body": e.response.text[:500]}
        )
        raise ValueError(
            "Unable to search for cabs at the moment. "
            "The cab service encountered an issue. "
            "Please try again with a different date/time or route."
        )
    except Exception as e:
        logger.error(
            "Unexpected error calling Search API",
            extra={"error": str(e), "error_type": type(e).__name__},
            exc_info=True,
        )
        raise ValueError(
            "Something went wrong while searching for cabs. "
            "Please try again in a moment."
        )


async def hold_cab(payload: dict) -> HoldAPIResponse:
    """POST to the Hold API and return a parsed HoldAPIResponse."""
    logger.info(
        "Calling Hold API",
        extra={"url": HOLD_API_URL, "searchId": payload.get("searchId")}
    )

    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            response = await client.post(
                HOLD_API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

        result = HoldAPIResponse(**data)
        logger.info(
            "Hold API response received",
            extra={"bookingId": result.bookingId}
        )
        return result

    except httpx.TimeoutException:
        logger.error("Hold API request timed out", extra={"url": HOLD_API_URL})
        raise ValueError(
            "The cab reservation service is taking too long to respond. "
            "Please try again in a moment."
        )
    except httpx.HTTPStatusError as e:
        logger.error(
            "Hold API returned error status",
            extra={"status_code": e.response.status_code, "body": e.response.text[:500]}
        )
        raise ValueError(
            "Unable to reserve this cab at the moment. "
            "The cab may no longer be available. "
            "Please search again and try a different option."
        )
    except Exception as e:
        logger.error(
            "Unexpected error calling Hold API",
            extra={"error": str(e), "error_type": type(e).__name__},
            exc_info=True,
        )
        raise ValueError(
            "Something went wrong while reserving the cab. "
            "Please try again in a moment."
        )

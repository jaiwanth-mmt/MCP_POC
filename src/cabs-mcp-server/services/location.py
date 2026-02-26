import os
from typing import Optional

import httpx
from dotenv import load_dotenv

from models.models import LocationOption, LocationObject
from services.logging_config import get_logger

load_dotenv()

logger = get_logger(__name__, service="location")

GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
PLACES_AUTOCOMPLETE_URL = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
LOCATION_API_URL = "http://cabs-search.ecs.mmt/google/v2/location/legacy"

if not GOOGLE_PLACES_API_KEY:
    logger.error("GOOGLE_PLACES_API_KEY not found in environment variables")


async def geocode_location(query: str) -> list[LocationOption]:
    """Call Google Places Autocomplete to get place suggestions."""
    if not query or not query.strip():
        logger.warning("Received empty geocoding query")
        return []

    if not GOOGLE_PLACES_API_KEY:
        logger.error("GOOGLE_PLACES_API_KEY not configured")
        raise ValueError("Location service is not configured. Please contact administrator.")

    try:
        logger.debug(
            "Sending autocomplete request to Google Places API",
            extra={"query": query}
        )

        params = {
            "input": query,
            "key": GOOGLE_PLACES_API_KEY,
            "types": "geocode|establishment",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(PLACES_AUTOCOMPLETE_URL, params=params)
            response.raise_for_status()
            data = response.json()

        if data.get("status") != "OK":
            logger.warning(
                "Google Places API returned non-OK status",
                extra={"status": data.get("status"), "query": query}
            )
            return []

        predictions = data.get("predictions", [])
        logger.info(
            "Autocomplete successful",
            extra={"query": query, "results_count": len(predictions)}
        )

        location_options = []
        for prediction in predictions:
            location_options.append(LocationOption(
                place_id=prediction["place_id"],
                formatted_address=prediction["description"],
                name=prediction.get("structured_formatting", {}).get(
                    "main_text", prediction["description"]
                ),
            ))

        return location_options

    except httpx.TimeoutException:
        logger.error("Geocoding request timed out", extra={"query": query})
        return []
    except httpx.HTTPError as e:
        logger.error("HTTP error during geocoding", extra={"query": query, "error": str(e)})
        return []
    except Exception as e:
        logger.error(
            "Unexpected error during geocoding",
            extra={"query": query, "error": str(e), "error_type": type(e).__name__},
            exc_info=True,
        )
        return []


async def resolve_location_by_place_id(place_id: str) -> Optional[LocationObject]:
    """
    Call the Location API to get the full location object for a place_id.
    Returns a LocationObject matching the shape the Search API expects.
    """
    if not place_id:
        logger.warning("Received empty place_id for resolution")
        return None

    try:
        logger.debug("Resolving location via Location API", extra={"place_id": place_id})

        params = {"placeId": place_id}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(LOCATION_API_URL, params=params)
            response.raise_for_status()
            data = response.json()

        location = LocationObject(
            pincode=data.get("pincode"),
            country=data.get("country"),
            address=data.get("address"),
            city=data.get("city"),
            secondary_text=data.get("secondary_text"),
            latitude=data.get("latitude"),
            is_airport=data.get("is_airport"),
            city_code=data.get("city_code"),
            label=data.get("label"),
            country_code=data.get("country_code"),
            is_city=data.get("is_city"),
            google_city=data.get("google_city"),
            locusV2Id=data.get("locusV2Id"),
            name=data.get("name"),
            mainText=data.get("mainText"),
            main_text=data.get("main_text"),
            state=data.get("state"),
            locusV2Type=data.get("locusV2Type"),
            place_id=data.get("place_id", place_id),
            longitude=data.get("longitude"),
        )

        logger.info(
            "Location resolved successfully",
            extra={
                "place_id": place_id,
                "address": location.address,
                "lat": location.latitude,
                "lng": location.longitude,
            }
        )
        return location

    except httpx.TimeoutException:
        logger.error("Location API request timed out", extra={"place_id": place_id})
        return None
    except httpx.HTTPError as e:
        logger.error(
            "HTTP error during location resolution",
            extra={"place_id": place_id, "error": str(e)},
            exc_info=True,
        )
        return None
    except Exception as e:
        logger.error(
            "Unexpected error during location resolution",
            extra={"place_id": place_id, "error": str(e), "error_type": type(e).__name__},
            exc_info=True,
        )
        return None


def build_disambiguation_response(
    location_type: str,
    query: str,
    options: list[LocationOption],
) -> dict:
    """
    Build a disambiguation response for Claude to present to the user.
    Returns a dict that the tool returns instead of search results.
    """
    numbered_options = []
    for i, loc in enumerate(options, 1):
        numbered_options.append({
            "option_number": i,
            "name": loc.name,
            "address": loc.formatted_address,
            "place_id": loc.place_id,
        })

    return {
        "status": "disambiguation_needed",
        "location_type": location_type,
        "query": query,
        "message": (
            f"Multiple locations found for {location_type}: '{query}'. "
            f"Please ask the user to select one option by number, "
            f"or say 'none' if none of these match (in that case, ask the user to provide a more specific location). "
            f"Then call search_cabs again with the selected place_id "
            f"in the '{location_type}_place_id' field."
        ),
        "options": numbered_options,
    }


async def resolve_location(
    location_query: str,
    location_type: str,
    place_id: Optional[str] = None,
) -> tuple[Optional[LocationObject], Optional[dict], Optional[str]]:
    """
    Resolve a location query into a full LocationObject.

    If place_id is provided, resolves directly via the Location API.
    Otherwise, uses Google Places Autocomplete to find candidates.

    Returns a 3-tuple:
      (LocationObject, None, None)        -- resolved successfully
      (None, disambiguation_dict, None)   -- multiple matches, needs user selection
      (None, None, error_message)         -- failed
    """
    # Direct resolution via place_id (user already selected from disambiguation)
    if place_id:
        logger.info(
            "Resolving location directly via place_id",
            extra={"place_id": place_id, "type": location_type}
        )
        location = await resolve_location_by_place_id(place_id)
        if not location:
            return None, None, f"Failed to resolve {location_type} location for the selected place. Please try a different search."
        return location, None, None

    # Search via Google Places Autocomplete
    logger.info(
        "Starting location resolution via autocomplete",
        extra={"query": location_query, "type": location_type}
    )

    results = await geocode_location(location_query)

    if not results:
        logger.warning(
            "No geocoding results found",
            extra={"query": location_query, "type": location_type}
        )
        return None, None, f"No locations found for {location_type}: '{location_query}'. Please try a more specific location name."

    if len(results) == 1:
        loc = results[0]
        logger.debug(
            "Single location match, resolving details",
            extra={"place_id": loc.place_id, "location_name": loc.name}
        )
        location = await resolve_location_by_place_id(loc.place_id)
        if not location:
            return None, None, f"Failed to get details for {location_type}: '{loc.name}'. Please try again."
        logger.info(
            "Location resolved successfully",
            extra={"address": location.address, "lat": location.latitude, "lng": location.longitude}
        )
        return location, None, None

    # Multiple results -- return disambiguation options for Claude
    logger.info(
        "Multiple locations found, returning disambiguation options",
        extra={"count": len(results), "type": location_type}
    )
    disambiguation = build_disambiguation_response(location_type, location_query, results)
    return None, disambiguation, None

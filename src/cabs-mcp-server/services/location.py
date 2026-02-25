import os
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastmcp import Context

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
            pincode=data.get("pincode", ""),
            country=data.get("country", ""),
            address=data.get("address", ""),
            city=data.get("city", ""),
            secondary_text=data.get("secondary_text"),
            latitude=data.get("latitude", 0.0),
            is_airport=data.get("is_airport", False),
            city_code=data.get("city_code"),
            label=data.get("label"),
            country_code=data.get("country_code", ""),
            is_city=data.get("is_city", False),
            google_city=data.get("google_city"),
            locusV2Id=data.get("locusV2Id", ""),
            name=data.get("name"),
            mainText=data.get("mainText"),
            main_text=data.get("main_text"),
            state=data.get("state", ""),
            locusV2Type=data.get("locusV2Type", ""),
            place_id=data.get("place_id", place_id),
            longitude=data.get("longitude", 0.0),
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


async def get_location_with_disambiguation(
    ctx: Context,
    location_query: str,
    location_type: str,
) -> tuple[Optional[LocationObject], Optional[str]]:
    """
    Resolve a user's location query into a full LocationObject.

    Uses Google Places Autocomplete for suggestions, elicitation for
    disambiguation when multiple results match, and the Location API
    to fetch the complete location object.

    Returns (LocationObject, None) on success or (None, error_message) on failure.
    """
    logger.info(
        "Starting location resolution",
        extra={"query": location_query, "type": location_type}
    )

    results = await geocode_location(location_query)

    if not results:
        logger.warning(
            "No geocoding results found",
            extra={"query": location_query, "type": location_type}
        )
        return None, f"No locations found for {location_type}: {location_query}"

    if len(results) == 1:
        loc = results[0]
        logger.debug(
            "Single location match, resolving details",
            extra={"place_id": loc.place_id, "location_name": loc.name}
        )
        location = await resolve_location_by_place_id(loc.place_id)
        if not location:
            logger.error(
                "Failed to resolve location details",
                extra={"place_id": loc.place_id, "location_name": loc.name}
            )
            return None, f"Failed to get details for {location_type}: '{loc.name}'. Please try again."
        logger.info(
            "Location resolved successfully",
            extra={"address": location.address, "lat": location.latitude, "lng": location.longitude}
        )
        return location, None

    # Multiple results — ask the user to pick one
    logger.info(
        "Multiple locations found, requesting user disambiguation",
        extra={"count": len(results), "type": location_type}
    )

    options_dict = {
        loc.place_id: {
            "title": f"{loc.name} - {loc.formatted_address}"
        }
        for loc in results
    }

    options_dict["__CUSTOM__"] = {
        "title": "None of these - let me specify a different location"
    }

    response = await ctx.elicit(
        message=f"Found {len(results)} locations for '{location_query}'. "
                f"Please select the {location_type} location:",
        response_type=options_dict,
    )

    place_id = response.data

    if not place_id:
        logger.warning(f"User did not select any location", extra={"type": location_type})
        return None, f"No {location_type} location selected"

    if place_id == "__CUSTOM__":
        logger.info(f"User opted for custom location entry", extra={"type": location_type})
        custom_response = await ctx.elicit(
            message=f"Please enter a more specific {location_type} location:\n"
                    f"Tip: Include area, landmark, or sector "
                    f"(e.g., 'Mumbai Airport Terminal 2', 'Noida Sector 62')",
            response_type=str,
        )
        custom_location_query = custom_response.data

        if not custom_location_query:
            logger.warning(f"User provided empty custom location", extra={"type": location_type})
            return None, f"No custom {location_type} location provided"

        logger.info(
            "Retrying geocoding with custom input",
            extra={"original_query": location_query, "custom_query": custom_location_query}
        )
        return await get_location_with_disambiguation(ctx, custom_location_query, location_type)

    # User selected a specific place_id
    location = await resolve_location_by_place_id(place_id)
    if not location:
        logger.error(
            "Failed to resolve selected location",
            extra={"place_id": place_id, "type": location_type}
        )
        return None, f"Failed to resolve {location_type} location. Please try a different search."

    logger.info(
        "User selection resolved successfully",
        extra={"address": location.address, "place_id": place_id}
    )
    return location, None

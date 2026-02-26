from dotenv import load_dotenv
load_dotenv()

import os
from datetime import datetime

from fastmcp import FastMCP, Context

from models.models import (
    SearchRequest,
    SearchAPIResponse,
    HoldRequest,
    HoldAPIResponse,
)
from services.logging_config import get_logger, setup_logging
from services.location import resolve_location
from services import api_client

log_level = os.getenv("LOG_LEVEL", "INFO")
setup_logging(level=log_level, use_stderr=True)
logger = get_logger(__name__, service="mcp-cab-server")

mcp = FastMCP("cab-server")


def parse_pickup_datetime(date_str: str, time_str: str) -> int:
    """
    Parse human-readable date and time strings into epoch milliseconds.

    Supported date formats: dd-MM-yyyy, yyyy-MM-dd
    Supported time formats: HH:MM, H:MM AM/PM, HH:MM AM/PM
    """
    parsed_date = None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            parsed_date = datetime.strptime(date_str.strip(), fmt).date()
            break
        except ValueError:
            continue

    if parsed_date is None:
        raise ValueError(
            f"Invalid date format: '{date_str}'. Use dd-MM-yyyy or yyyy-MM-dd."
        )

    parsed_time = None
    time_str_clean = time_str.strip()
    for fmt in ("%H:%M", "%I:%M %p", "%I:%M%p"):
        try:
            parsed_time = datetime.strptime(time_str_clean, fmt).time()
            break
        except ValueError:
            continue

    if parsed_time is None:
        raise ValueError(
            f"Invalid time format: '{time_str}'. Use HH:MM (24h) or H:MM AM/PM."
        )

    dt = datetime.combine(parsed_date, parsed_time)
    return int(dt.timestamp() * 1000)


@mcp.tool(
    name="search_cabs",
    description=(
        "Search available cabs between source and destination. "
        "IMPORTANT: Do NOT assume or guess any input values. "
        "Always ask the user explicitly for: source location, destination location, travel date, and pickup time. "
        "Never use default or assumed values for date and time - the user must provide them. "
        "If the tool returns a disambiguation_needed response with location options, "
        "present the numbered options to the user and ask them to pick one (or say 'none' for a different location). "
        "Then call this tool again with the selected place_id in source_place_id or destination_place_id. "
        "If the response has status 'no_cabs_found', apologize politely and share the message and suggestion. "
        "Never say 'server error' or show raw error codes to the user."
    ),
)
async def search_cabs(ctx: Context, input: SearchRequest) -> dict:
    logger.info(
        "Cab search request received",
        extra={"source": input.source, "destination": input.destination}
    )

    # Resolve source location
    try:
        source_location, source_disambiguation, source_error = await resolve_location(
            input.source, "source", input.source_place_id
        )
        if source_disambiguation:
            logger.info("Source disambiguation needed, returning options")
            return source_disambiguation
        if source_error:
            logger.error("Source location resolution failed", extra={"error": source_error})
            return {"status": "error", "message": source_error}
    except ValueError as e:
        logger.error("System error during source resolution", extra={"error": str(e)})
        return {"status": "error", "message": str(e)}

    # Resolve destination location
    try:
        dest_location, dest_disambiguation, dest_error = await resolve_location(
            input.destination, "destination", input.destination_place_id
        )
        if dest_disambiguation:
            logger.info("Destination disambiguation needed, returning options")
            return dest_disambiguation
        if dest_error:
            logger.error("Destination location resolution failed", extra={"error": dest_error})
            return {"status": "error", "message": dest_error}
    except ValueError as e:
        logger.error("System error during destination resolution", extra={"error": str(e)})
        return {"status": "error", "message": str(e)}

    # Convert date + time to epoch milliseconds
    try:
        pickup_time_ms = parse_pickup_datetime(input.date, input.time)
    except ValueError as e:
        logger.error("Date/time parsing failed", extra={"error": str(e)})
        return {"status": "error", "message": str(e)}

    # Build source payload with sourceText
    source_dict = source_location.model_dump()
    source_dict["sourceText"] = source_location.address

    # Build destination payload with destinationText
    dest_dict = dest_location.model_dump()
    dest_dict["destinationText"] = dest_location.address

    payload = {
        "source": source_dict,
        "destination": dest_dict,
        "pickupTime": pickup_time_ms,
    }

    logger.info(
        "Both locations resolved, calling Search API",
        extra={
            "source_address": source_location.address,
            "dest_address": dest_location.address,
            "pickupTime": pickup_time_ms,
        }
    )

    try:
        result = await api_client.search_cabs(payload)
    except ValueError as e:
        logger.error("Search API call failed", extra={"error": str(e)})
        return {
            "status": "no_cabs_found",
            "message": str(e),
            "suggestion": "You can try changing the date, time, or locations and search again.",
        }

    if not result.cabs:
        logger.warning(
            "No cabs available for route",
            extra={
                "source": source_location.address,
                "destination": dest_location.address,
            }
        )
        return {
            "status": "no_cabs_found",
            "message": (
                f"No cabs are currently available from {source_location.address} "
                f"to {dest_location.address} at the requested date and time."
            ),
            "suggestion": "You can try a different date, time, or nearby pickup/drop location.",
        }

    logger.info(
        "Search completed",
        extra={
            "count": len(result.cabs),
            "searchId": result.searchId,
            "distance_km": result.totalDistanceInKm,
        }
    )

    return result.model_dump()


@mcp.tool(
    name="hold_cab",
    description=(
        "Reserve a selected cab with passenger and contact details. "
        "IMPORTANT: Do NOT assume or guess any user-provided input values. "
        "The system fields (search_id, cab_id, category_id) come from the search results - do not ask the user for these. "
        "But you MUST ask the user explicitly for: first name, last name, gender, email, and mobile number. "
        "Never assume or fill in passenger or contact details on your own. "
        "If the response has status 'hold_failed', apologize politely and share the message and suggestion. "
        "Never say 'server error' or show raw error codes to the user. "
        "On SUCCESS, present the response EXACTLY in this format:\n"
        "1. Show 'Here are your booking details:' followed by the passenger details (name, gender, email, mobile).\n"
        "2. Say 'Pay through the link below to get your booking confirmed:' and show the paymentUrl.\n"
        "3. Say 'After payment, you can track your booking on MakeMyTrip with the same details you provided above.'\n"
        "4. Show MakeMyTrip link: https://www.makemytrip.com/\n"
        "NEVER say 'Booking confirmed' — the booking is NOT confirmed until the user pays."
    ),
)
async def hold_cab(ctx: Context, input: HoldRequest) -> dict:
    logger.info(
        "Hold cab request received",
        extra={
            "search_id": input.search_id,
            "cab_id": input.cab_id,
            "category_id": input.category_id,
            "passenger": input.first_name,
        }
    )

    payload = {
        "searchId": input.search_id,
        "categoryId": input.category_id,
        "cabId": input.cab_id,
        "passengerDetail": {
            "first_name": input.first_name,
            "last_name": input.last_name,
            "gender": input.gender,
        },
        "contactDetails": {
            "email_id": input.email,
            "mobile": input.mobile,
            "country_code": "+91",
        },
    }

    try:
        result = await api_client.hold_cab(payload)
    except ValueError as e:
        logger.error(
            "Hold API call failed",
            extra={"search_id": input.search_id, "error": str(e)}
        )
        return {
            "status": "hold_failed",
            "message": str(e),
            "suggestion": "You can search again for available cabs and try reserving a different one.",
        }

    logger.info(
        "Cab hold successful",
        extra={
            "bookingId": result.bookingId,
            "search_id": input.search_id,
        }
    )

    return {
        "status": "success",
        "bookingId": result.bookingId,
        "paymentUrl": result.paymentUrl,
        "passengerDetails": {
            "name": f"{input.first_name} {input.last_name}".strip(),
            "gender": input.gender,
            "email": input.email,
            "mobile": f"+91 {input.mobile}",
        },
        "makemytripUrl": "https://www.makemytrip.com/",
    }


if __name__ == "__main__":
    mcp.run()

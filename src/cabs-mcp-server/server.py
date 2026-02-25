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
from services.location import get_location_with_disambiguation
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


@mcp.tool(name="search_cabs", description="Search available cabs between source and destination")
async def search_cabs(ctx: Context, input: SearchRequest) -> SearchAPIResponse:
    logger.info(
        "Cab search request received",
        extra={"source": input.source, "destination": input.destination}
    )

    # Resolve source location
    try:
        source_location, source_error = await get_location_with_disambiguation(
            ctx, input.source, "source"
        )
        if source_error:
            logger.error(
                "Source location resolution failed",
                extra={"query": input.source, "error": source_error}
            )
            await ctx.info(f"Source location error: {source_error}")
            return SearchAPIResponse(
                searchId="", totalDistanceInKm=0, totalApproxDurationInMin=0,
                cabAvailabilityTime=0, cabs=[],
            )
    except ValueError as e:
        logger.error("System error during source resolution", extra={"error": str(e)})
        await ctx.info(f"System error: {str(e)}")
        return SearchAPIResponse(
            searchId="", totalDistanceInKm=0, totalApproxDurationInMin=0,
            cabAvailabilityTime=0, cabs=[],
        )

    # Resolve destination location
    try:
        dest_location, dest_error = await get_location_with_disambiguation(
            ctx, input.destination, "destination"
        )
        if dest_error:
            logger.error(
                "Destination location resolution failed",
                extra={"query": input.destination, "error": dest_error}
            )
            await ctx.info(f"Destination location error: {dest_error}")
            return SearchAPIResponse(
                searchId="", totalDistanceInKm=0, totalApproxDurationInMin=0,
                cabAvailabilityTime=0, cabs=[],
            )
    except ValueError as e:
        logger.error("System error during destination resolution", extra={"error": str(e)})
        await ctx.info(f"System error: {str(e)}")
        return SearchAPIResponse(
            searchId="", totalDistanceInKm=0, totalApproxDurationInMin=0,
            cabAvailabilityTime=0, cabs=[],
        )

    # Convert date + time to epoch milliseconds
    try:
        pickup_time_ms = parse_pickup_datetime(input.date, input.time)
    except ValueError as e:
        logger.error("Date/time parsing failed", extra={"error": str(e)})
        await ctx.info(f"Date/time error: {str(e)}")
        return SearchAPIResponse(
            searchId="", totalDistanceInKm=0, totalApproxDurationInMin=0,
            cabAvailabilityTime=0, cabs=[],
        )

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
        await ctx.info(f"Search error: {str(e)}")
        return SearchAPIResponse(
            searchId="", totalDistanceInKm=0, totalApproxDurationInMin=0,
            cabAvailabilityTime=0, cabs=[],
        )

    if not result.cabs:
        logger.warning(
            "No cabs available for route",
            extra={
                "source": source_location.address,
                "destination": dest_location.address,
            }
        )
        await ctx.info(
            f"No cabs available for route:\n"
            f"From: {source_location.address}\n"
            f"To: {dest_location.address}\n"
            f"Please try a different route or time."
        )
    else:
        logger.info(
            "Cabs found",
            extra={
                "count": len(result.cabs),
                "searchId": result.searchId,
                "distance_km": result.totalDistanceInKm,
            }
        )

    return result


@mcp.tool(name="hold_cab", description="Reserve a selected cab with passenger and contact details")
async def hold_cab(ctx: Context, input: HoldRequest) -> HoldAPIResponse:
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
            "gender": input.gender.strip().upper(),
        },
        "contactDetails": {
            "email_id": input.email.strip().lower(),
            "mobile": input.mobile.replace(" ", "").replace("-", ""),
            "country_code": "+91",
        },
    }

    # Normalize mobile number to 10 digits
    mobile = payload["contactDetails"]["mobile"]
    if mobile.startswith("+91"):
        mobile = mobile[3:]
    elif mobile.startswith("91") and len(mobile) == 12:
        mobile = mobile[2:]
    payload["contactDetails"]["mobile"] = mobile

    try:
        result = await api_client.hold_cab(payload)
    except ValueError as e:
        logger.error(
            "Hold API call failed",
            extra={"search_id": input.search_id, "error": str(e)}
        )
        await ctx.info(f"Hold error: {str(e)}")
        raise

    logger.info(
        "Cab hold successful",
        extra={
            "bookingId": result.bookingId,
            "search_id": input.search_id,
        }
    )

    await ctx.info(
        f"Cab Reserved!\n\n"
        f"Booking ID: {result.bookingId}\n"
        f"Passenger: {input.first_name} {input.last_name}\n\n"
        f"Payment URL: {result.paymentUrl}\n\n"
        f"Please open this URL in your browser to complete payment."
    )

    return result


if __name__ == "__main__":
    mcp.run()

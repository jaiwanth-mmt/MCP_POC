from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator
import re


# ==================== LOCATION MODELS ====================

class LocationOption(BaseModel):
    """Place suggestion returned from Google Places Autocomplete."""
    place_id: str = Field(description="Google place_id")
    formatted_address: str = Field(description="Full formatted address")
    name: str = Field(description="Short name of the place")


class LocationObject(BaseModel):
    """
    Full location object matching the shape expected by the Search API.
    Populated from the Location API response.
    All string fields are Optional because the Location API may return null.
    """
    pincode: Optional[str] = Field(default=None)
    country: Optional[str] = Field(default=None)
    address: Optional[str] = Field(default=None)
    city: Optional[str] = Field(default=None)
    secondary_text: Optional[str] = Field(default=None)
    latitude: Optional[float] = Field(default=None)
    is_airport: Optional[bool] = Field(default=None)
    city_code: Optional[str] = Field(default=None)
    label: Optional[str] = Field(default=None)
    country_code: Optional[str] = Field(default=None)
    is_city: Optional[bool] = Field(default=None)
    google_city: Optional[str] = Field(default=None)
    locusV2Id: Optional[str] = Field(default=None)
    name: Optional[str] = Field(default=None)
    mainText: Optional[str] = Field(default=None)
    main_text: Optional[str] = Field(default=None)
    state: Optional[str] = Field(default=None)
    locusV2Type: Optional[str] = Field(default=None)
    place_id: Optional[str] = Field(default=None)
    longitude: Optional[float] = Field(default=None)


# ==================== SEARCH MODELS ====================

class SearchRequest(BaseModel):
    """User-facing input for the search_cabs tool."""
    source: str = Field(..., min_length=1, description="Pickup location text. Must be explicitly provided by the user, never assumed.")
    destination: str = Field(..., min_length=1, description="Drop location text. Must be explicitly provided by the user, never assumed.")
    date: str = Field(..., description="Date of journey (e.g. 28-02-2026 or 2026-02-28). Must be explicitly provided by the user, never assumed or defaulted.")
    time: str = Field(..., description="Time of pickup (e.g. 10:30 AM or 14:30). Must be explicitly provided by the user, never assumed or defaulted.")
    source_place_id: Optional[str] = Field(
        default=None,
        description="Google place_id for source. If provided, skips location search and resolves directly. Use this when the user has selected a specific location from disambiguation options."
    )
    destination_place_id: Optional[str] = Field(
        default=None,
        description="Google place_id for destination. If provided, skips location search and resolves directly. Use this when the user has selected a specific location from disambiguation options."
    )

    @field_validator("source", "destination")
    @classmethod
    def normalize_location(cls, v: str):
        return v.strip()


class SearchAPIPayload(BaseModel):
    """Payload sent to the backend Search API."""
    source: dict = Field(description="Resolved source location object")
    destination: dict = Field(description="Resolved destination location object")
    pickupTime: int = Field(description="Pickup time in epoch milliseconds")


class CabOption(BaseModel):
    """Single cab option from the Search API response."""
    id: str = Field(description="Cab identifier")
    categoryId: str = Field(description="Category identifier")
    modelName: str = Field(description="Vehicle model name")
    totalFare: float = Field(description="Total fare amount")
    seatCapacity: int = Field(description="Number of seats")
    luggageCapacity: int = Field(description="Luggage capacity")
    ac: bool = Field(description="Air conditioning available")
    rating: float = Field(description="Driver/cab rating")
    fuelType: str = Field(description="Fuel type (ELECTRIC, CNG, DIESEL, PETROL)")
    cabType: str = Field(description="Cab type (SEDAN, SUV, COMPACTSUV)")


class SearchAPIResponse(BaseModel):
    """Response from the backend Search API."""
    searchId: str = Field(description="Search session identifier")
    totalDistanceInKm: float = Field(description="Total route distance in km")
    totalApproxDurationInMin: float = Field(description="Approximate duration in minutes")
    cabAvailabilityTime: int = Field(description="Cab availability time in epoch ms")
    cabs: list[CabOption] = Field(description="List of available cab options")


# ==================== HOLD MODELS ====================

class PassengerDetail(BaseModel):
    """Passenger information for the Hold API."""
    first_name: str = Field(..., min_length=1, description="Passenger first name")
    last_name: str = Field(default="", description="Passenger last name")
    gender: str = Field(..., description="Gender (M/F)")

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str):
        v = v.strip().upper()
        if v not in ("M", "F"):
            raise ValueError("Gender must be M or F")
        return v


class ContactDetails(BaseModel):
    """Contact information for the Hold API."""
    email_id: str = Field(..., description="Email address")
    mobile: str = Field(..., description="Mobile number (10 digits)")
    country_code: str = Field(default="+91", description="Country code")

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, v: str):
        phone = v.replace(" ", "").replace("-", "")
        if phone.startswith("+91"):
            phone = phone[3:]
        elif phone.startswith("91") and len(phone) == 12:
            phone = phone[2:]
        if not re.match(r'^[6-9]\d{9}$', phone):
            raise ValueError(
                "Invalid mobile number. Must be 10 digits starting with 6-9."
            )
        return phone

    @field_validator("email_id")
    @classmethod
    def validate_email(cls, v: str):
        email = v.strip().lower()
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            raise ValueError("Invalid email format")
        return email


class HoldRequest(BaseModel):
    """User-facing input for the hold_cab tool."""
    search_id: str = Field(..., description="Search ID from search results. System-managed, do not ask the user.")
    cab_id: str = Field(..., description="Cab ID from search results. System-managed, do not ask the user.")
    category_id: str = Field(..., description="Category ID from search results. System-managed, do not ask the user.")
    first_name: str = Field(..., min_length=1, description="Passenger first name. Must be explicitly provided by the user, never assumed.")
    last_name: str = Field(default="", description="Passenger last name. Must be explicitly provided by the user, never assumed.")
    gender: str = Field(..., description="Gender (M/F/O — Male, Female, or Others). Must be explicitly provided by the user, never assumed.")
    email: str = Field(..., description="Email address. Must be explicitly provided by the user, never assumed.")
    mobile: str = Field(..., description="Mobile number (10 digits, starting with 6-9). Must be explicitly provided by the user, never assumed.")

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str):
        v = v.strip().upper()
        if v not in ("M", "F", "O"):
            raise ValueError("Gender must be M, F, or O")
        return v

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, v: str):
        phone = v.replace(" ", "").replace("-", "")
        if phone.startswith("+91"):
            phone = phone[3:]
        elif phone.startswith("91") and len(phone) == 12:
            phone = phone[2:]
        if not re.match(r'^[6-9]\d{9}$', phone):
            raise ValueError(
                "Invalid mobile number. Must be 10 digits starting with 6-9."
            )
        return phone

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str):
        email = v.strip().lower()
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            raise ValueError("Invalid email format")
        return email


class HoldAPIPayload(BaseModel):
    """Payload sent to the backend Hold API."""
    searchId: str
    categoryId: str
    cabId: str
    passengerDetail: PassengerDetail
    contactDetails: ContactDetails


class HoldAPIResponse(BaseModel):
    """Response from the backend Hold API."""
    bookingId: str = Field(description="Booking identifier")
    paymentUrl: str = Field(description="URL for payment completion")

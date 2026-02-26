# MCP Cab Server

An MCP (Model Context Protocol) server that lets AI assistants search and book cabs through natural conversation. Built with [FastMCP](https://gofastmcp.com) and backed by real Cab APIs.

## What It Does

This server exposes two tools to any MCP-compatible client (Claude Desktop, Cursor, etc.):

| Tool | Purpose |
|------|---------|
| `search_cabs` | Search available cabs between two locations for a given date and time |
| `hold_cab` | Reserve a selected cab with passenger details and get a payment link |

### Booking Flow

```
User: "Book a cab from Koramangala to Airport tomorrow at 3 PM"
  │
  ├─ 1. Location Resolution (Google Places → Location API)
  │     └─ If ambiguous, the assistant asks the user to pick from options
  │
  ├─ 2. Search Cabs (returns available options with fare, seats, luggage, etc.)
  │     └─ User picks a cab
  │
  ├─ 3. Collect Passenger Details (name, gender, email, mobile)
  │
  ├─ 4. Hold Cab (reserves the cab and returns a payment link)
  │
  └─ 5. User pays externally via the payment link
```

## Project Structure

```
POC_MCP/
├── main.py                          # Entry point — starts the MCP server
├── pyproject.toml                   # Dependencies and build config
├── .env                             # Environment variables (API keys)
└── src/cabs-mcp-server/
    ├── server.py                    # MCP tool definitions (search_cabs, hold_cab)
    ├── models/
    │   └── models.py                # Pydantic models for requests, responses, locations
    └── services/
        ├── api_client.py            # HTTP client for Search and Hold APIs
        ├── location.py              # Location resolution and disambiguation logic
        └── logging_config.py        # Structured colored logging
```

## Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** — fast Python package manager (recommended)
- **Google Places API Key** — for location autocomplete

## Setup

### 1. Clone and install dependencies

```bash
cd /path/to/POC_MCP
uv sync
```

### 2. Set up environment variables

Create a `.env` file in the project root:

```env
GOOGLE_PLACES_API_KEY=your_google_places_api_key_here
```

### 3. Test the server locally

```bash
uv run python main.py
```

The server starts in stdio mode (standard MCP transport). You should see `Starting MCP Cab Server...` in the output.

## Integrating with AI Clients

### Claude Desktop

Edit your Claude Desktop config file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Add the `cab-server` entry under `mcpServers`:

```json
{
  "mcpServers": {
    "cab-server": {
      "command": "/path/to/uv",
      "args": [
        "run",
        "--project",
        "/path/to/POC_MCP",
        "python",
        "/path/to/POC_MCP/main.py"
      ],
      "env": {
        "GOOGLE_PLACES_API_KEY": "your_google_places_api_key_here"
      }
    }
  }
}
```

Restart Claude Desktop to pick up the changes. The `search_cabs` and `hold_cab` tools will appear in the tools menu (hammer icon).

### Cursor

Edit your Cursor MCP config file:

- **macOS**: `~/.cursor/mcp.json`
- **Windows**: `%USERPROFILE%\.cursor\mcp.json`

Add the same `cab-server` entry:

```json
{
  "mcpServers": {
    "cab-server": {
      "command": "/path/to/uv",
      "args": [
        "run",
        "--project",
        "/path/to/POC_MCP",
        "python",
        "/path/to/POC_MCP/main.py"
      ],
      "env": {
        "GOOGLE_PLACES_API_KEY": "your_google_places_api_key_here"
      }
    }
  }
}
```

Restart Cursor (or reload the window) and the tools will be available in Agent mode.

### Finding your `uv` path

To get the absolute path to `uv` for the config above:

```bash
which uv
```

## How Location Resolution Works

When a user says a location like "Kadugodi", the server resolves it through these steps:

1. **Google Places Autocomplete** — converts text to place suggestions (with `place_id`s)
2. **If single match** — automatically resolves it via the Location API
3. **If multiple matches** — returns numbered options for the user to pick from
4. **After user picks** — the tool is called again with the selected `place_id`, which resolves directly

This means a search may take up to 3 conversational rounds if both source and destination are ambiguous.

## API Endpoints Used

| API | URL | Purpose |
|-----|-----|---------|
| Search | `POST /cabs/mcp/search` | Find available cabs for a route |
| Hold | `POST /cabs/mcp/hold` | Reserve a cab and get payment link |
| Location | `GET /google/v2/location/legacy` | Resolve a `place_id` to a full location object |
| Google Places | `GET /maps/api/place/autocomplete/json` | Autocomplete location text |

## Dependencies

| Package | Purpose |
|---------|---------|
| `fastmcp` | MCP server framework |
| `pydantic` | Data validation and serialization |
| `httpx` | Async HTTP client for API calls |
| `python-dotenv` | Load `.env` variables |
| `googlemaps` | Google Maps API support |

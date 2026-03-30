# Confluence Data Center MCP Server

MCP (Model Context Protocol) server for Confluence Data Center / Server. Enables AI assistants like Claude to interact with Confluence pages.

## Features

- Create Confluence pages with HTML or plain text content
- Add read/edit restrictions to pages (users and groups)
- Get and remove page restrictions
- Search pages using CQL or plain text across all spaces
- Read full content of a specific page
- List pages in a space with filtering
- Get child pages of a parent page
- Sync user directory with external directory (e.g., Active Directory)

## Available Tools

### `confluence_create_page`
Create a new page in a Confluence space.

### `confluence_add_restrictions`
Add read or edit restrictions to a page for specific users or groups.

### `confluence_get_restrictions`
Get current restrictions for a page.

### `confluence_remove_restrictions`
Remove restrictions from a page.

### `confluence_get_space_pages`
List all pages in a space with optional title filtering.

### `confluence_get_child_pages`
Get all child pages of a specific parent page.

### `confluence_search_pages`
Search pages across all spaces (or a specific space) using plain text or CQL (Confluence Query Language).

Supports plain text queries as well as full CQL expressions:
- `"deployment guide"` — full-text search
- `title ~ "Meeting Notes"` — search in titles
- `space = "TEAM" AND text ~ "roadmap"` — CQL with space filter
- `space = "DOCS" AND lastmodified >= "2024-01-01"` — date filtering

### `confluence_get_page`
Read the full content and metadata of a specific page. Can be identified by `page_id` or by `page_title` + `space_key`. Set `include_content=false` to retrieve only metadata without the full HTML body.

### `confluence_sync_user_directory`
Trigger synchronization of user directory with external directory (requires admin privileges).



## Usage Examples

Once configured, you can use natural language commands with Claude:

- "Create a new page in TEAM space titled 'Meeting Notes'"
- "Add edit restrictions to page ID 12345 for group 'developers'"
- "Add view and edit restrictions to page IT-DEV for group 'developers' in TEAM space"
- "Search all pages in space TEAM and list only pages without restrictions"
- "Search for pages about 'deployment guide' across all spaces"
- "Find all pages with 'Meeting' in the title in TEAM space"
- "Read the content of page titled 'Architecture Overview' in DOCS space"
- "List all pages in the DOCS space"
- "Sync the Confluence user directory"





## Requirements

- Python 3.10+
- Claude
- Confluence Data Center or Server instance
- API user token or user credentials

## Installing uv (Recommended)

`uv` is an extremely fast Python package manager that simplifies running MCP servers. With `uv`, you don't need to manually create virtual environments or install dependencies - it handles everything automatically.

### macOS / Linux

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### macOS (Homebrew)

```bash
brew install uv
```

### Windows

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Verify installation

```bash
uv --version
```

> **Note:** Using `uv` is optional but recommended. If you prefer not to use it, you can use the standard `python` + `pip install` approach instead.

## Installation

1. Clone the repository:
```bash
git clone https://github.com/marekudlacek/mcp-confluence-datacenter.git
cd mcp-confluence-datacenter
```

2. Install dependencies (! only when uv is not used !):
```bash
pip install -r requirements.txt
```

## Configuration

Set the following environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `CONFLUENCE_URL` | Yes | Your Confluence URL (e.g., `https://confluence.company.com`) |
| `CONFLUENCE_LOGIN` | Yes | Your Confluence username |
| `CONFLUENCE_API_TOKEN` | Yes | Your Confluence API token or password |
| `CONFLUENCE_LOGIN_PASSWORD` | For sync | Admin password (required for user directory sync) |
| `CONFLUENCE_DIRECTORY_ID` | For sync | Directory ID for user directory sync |

## Setup for Claude Code

Add to your `~/.claude.json` or project's `.claude.json`:

```json
{
  "mcpServers": {
    "confluence": {
      "command": "python",
      "args": ["/path/to/mcp-confluence-datacenter.py"],
      "env": {
        "CONFLUENCE_URL": "https://confluence.your-company.com",
        "CONFLUENCE_LOGIN": "your-username",
        "CONFLUENCE_API_TOKEN": "your-api-token",
        "CONFLUENCE_LOGIN_PASSWORD": "your-password",
        "CONFLUENCE_DIRECTORY_ID": "your-directory-id"
      }
    }
  }
}
```

Or with `uv` (recommended):

```json
{
  "mcpServers": {
    "confluence": {
      "command": "uv",
      "args": [
        "run",
        "--with", "httpx",
        "--with", "pydantic",
        "--with", "mcp",
        "python",
        "/path/to/mcp-confluence-datacenter.py"
      ],
      "env": {
        "CONFLUENCE_URL": "https://confluence.your-company.com",
        "CONFLUENCE_LOGIN": "your-username",
        "CONFLUENCE_API_TOKEN": "your-api-token",
        "CONFLUENCE_LOGIN_PASSWORD": "your-password",
        "CONFLUENCE_DIRECTORY_ID": "your-directory-id"
      }
    }
  }
}
```

# Setup for Claude Desktop

## Quick Install via CLI

You can add this MCP server directly using the `claude mcp add` command.

### With uv (recommended):

```bash
claude mcp add --transport stdio confluence \
  --env CONFLUENCE_URL=https://confluence.your-company.com \
  --env CONFLUENCE_LOGIN=your-username \
  --env CONFLUENCE_API_TOKEN=your-api-token \
  --env CONFLUENCE_LOGIN_PASSWORD=your-password \
  --env CONFLUENCE_DIRECTORY_ID=your-directory-id \
  -- uv run --with httpx --with pydantic --with mcp python /path/to/mcp-confluence-datacenter.py
```

### With python:

```bash
claude mcp add --transport stdio confluence \
  --env CONFLUENCE_URL=https://confluence.your-company.com \
  --env CONFLUENCE_LOGIN=your-username \
  --env CONFLUENCE_API_TOKEN=your-api-token \
  --env CONFLUENCE_LOGIN_PASSWORD=your-password \
  --env CONFLUENCE_DIRECTORY_ID=your-directory-id \
  -- python /path/to/mcp-confluence-datacenter.py
```

### Manage MCP servers:

```bash
# List all configured servers
claude mcp list

# Get details for a specific server
claude mcp get confluence

# Remove a server
claude mcp remove confluence
```

## Install via CONFIG FILES


Add to your Claude Desktop configuration file:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "confluence": {
      "command": "python",
      "args": ["/path/to/mcp-confluence-datacenter.py"],
      "env": {
        "CONFLUENCE_URL": "https://confluence.your-company.com",
        "CONFLUENCE_LOGIN": "your-username",
        "CONFLUENCE_API_TOKEN": "your-api-token",
        "CONFLUENCE_LOGIN_PASSWORD": "your-password",
        "CONFLUENCE_DIRECTORY_ID": "your-directory-id"
      }
    }
  }
}
```

Or with `uv` (recommended):

```json
{
  "mcpServers": {
    "confluence": {
      "command": "uv",
      "args": [
        "run",
        "--with", "httpx",
        "--with", "pydantic",
        "--with", "mcp",
        "python",
        "/path/to/mcp-confluence-datacenter.py"
      ],
      "env": {
        "CONFLUENCE_URL": "https://confluence.your-company.com",
        "CONFLUENCE_LOGIN": "your-username",
        "CONFLUENCE_API_TOKEN": "your-api-token",
        "CONFLUENCE_LOGIN_PASSWORD": "your-password",
        "CONFLUENCE_DIRECTORY_ID": "your-directory-id"
      }
    }
  }
}
```



## License

MIT License

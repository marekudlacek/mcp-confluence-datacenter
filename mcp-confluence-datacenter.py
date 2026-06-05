"""
Confluence Creator MCP Server (Extended)

This MCP server enables creating Confluence pages with content restrictions.
It provides tools for:
- Creating pages with generated or custom content
- Adding read/edit restrictions for users and groups
- Managing page permissions
- Searching and listing pages in a space
- Managing comments and labels
- Deleting pages

Requirements:
- CONFLUENCE_URL: Your Confluence DC URL (e.g., https://confluence.your-domain.com)
- CONFLUENCE_LOGIN: Your Confluence username
- CONFLUENCE_API_TOKEN: Your Confluence personal access token
"""

import os
import json
import re
import httpx
try:
    import html2text as _html2text_module
    _HTML2TEXT_AVAILABLE = True
except ImportError:
    _HTML2TEXT_AVAILABLE = False

try:
    import markdown as _markdown_module
    _MARKDOWN_AVAILABLE = True
except ImportError:
    _MARKDOWN_AVAILABLE = False

from typing import Optional, List, Literal
from enum import Enum
from pydantic import BaseModel, Field, field_validator, ConfigDict
from mcp.server.fastmcp import FastMCP

# Initialize MCP server
mcp = FastMCP("confluence_creator_mcp_extended")

# Configuration
CONFLUENCE_URL = os.getenv("CONFLUENCE_URL", "").rstrip("/")
CONFLUENCE_LOGIN = os.getenv("CONFLUENCE_LOGIN", "")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN", "")

# Sync configuration (for user directory sync - requires admin credentials)
CONFLUENCE_LOGIN_PASSWORD = os.getenv("CONFLUENCE_LOGIN_PASSWORD", "")
CONFLUENCE_DIRECTORY_ID = os.getenv("CONFLUENCE_DIRECTORY_ID", "")

# Singleton HTTP client
_http_client: Optional[httpx.AsyncClient] = None


def get_http_client() -> httpx.AsyncClient: 
    """Get or create singleton HTTP client for Confluence API."""
    global _http_client
    if _http_client is None:
        if not all([CONFLUENCE_URL, CONFLUENCE_API_TOKEN]):
            raise ValueError(
                "Missing required environment variables: "
                "CONFLUENCE_URL, CONFLUENCE_API_TOKEN"
            )
        _http_client = httpx.AsyncClient(
            base_url=CONFLUENCE_URL,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {CONFLUENCE_API_TOKEN}",
            },
            timeout=30.0,
        )
    return _http_client


def _handle_api_error(e: Exception) -> str:
    """Format API errors consistently."""
    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code
        if status == 400:
            return f"Error: Bad request - {e.response.text}"
        elif status == 401:
            return "Error: Authentication failed. Check your API token and email."
        elif status == 403:
            return "Error: Permission denied. You don't have access to perform this operation."
        elif status == 404:
            return "Error: Resource not found. Check the space key or page ID."
        elif status == 429:
            return "Error: Rate limit exceeded. Please wait before making more requests."
        return f"Error: API request failed with status {status}: {e.response.text}"
    elif isinstance(e, httpx.TimeoutException):
        return "Error: Request timed out. Please try again."
    elif isinstance(e, ValueError):
        return f"Error: {str(e)}"
    return f"Error: Unexpected error occurred: {type(e).__name__} - {str(e)}"


class EditorVersion(str, Enum):
    """Confluence editor version."""
    V1 = "v1"  # Old editor
    V2 = "v2"  # New editor (default)


class OperationType(str, Enum):
    """Restriction operation types."""
    READ = "read"
    UPDATE = "update"


class CreatePageInput(BaseModel):
    """Input for creating a Confluence page."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    space_key: str = Field(
        ...,
        description="Space key where the page will be created (e.g., 'TEAM', 'DOCS')",
        min_length=1,
        max_length=255
    )
    title: str = Field(
        ...,
        description="Title of the new page",
        min_length=1,
        max_length=255
    )
    content: str = Field(
        ...,
        description="Page content in HTML/storage format or plain text. For plain text, it will be wrapped in <p> tags.",
        min_length=1
    )
    parent_id: Optional[str] = Field(
        default=None,
        description="Optional parent page ID to create this page as a child"
    )
    parent_title: Optional[str] = Field(
        default=None,
        description="Optional parent page title to create this page as a child (alternative to parent_id)"
    )
    editor_version: EditorVersion = Field(
        default=EditorVersion.V2,
        description="Editor version to use: 'v1' for old editor, 'v2' for new editor (default)"
    )
    content_format: Literal["storage", "markdown", "wiki"] = Field(
        default="storage",
        description="Input format of content: 'storage' (raw HTML, default), 'markdown', or 'wiki'"
    )

    @field_validator('parent_title')
    @classmethod
    def check_parent_exclusivity(cls, v: Optional[str], info) -> Optional[str]:
        """Ensure only one of parent_id or parent_title is provided."""
        # Note: This validator only sees the current field, full validation is done in the tool
        return v


class AddRestrictionInput(BaseModel):
    """Input for adding restrictions to a page."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    page_id: Optional[str] = Field(
        default=None,
        description="ID of the page to add restrictions to",
        min_length=1
    )
    page_title: Optional[str] = Field(
        default=None,
        description="Title of the page to add restrictions to (alternative to page_id)",
        min_length=1
    )
    space_key: Optional[str] = Field(
        default=None,
        description="Space key (required when using page_title)",
        min_length=1
    )
    operation: OperationType = Field(
        ...,
        description="Type of restriction: 'read' for viewing, 'update' for editing"
    )
    user_account_ids: Optional[List[str]] = Field(
        default=None,
        description="List of user account IDs to grant permission to",
        max_items=50
    )
    user_identifiers: Optional[List[str]] = Field(
        default=None,
        description="List of usernames or emails to grant permission to (alternative to user_account_ids)",
        max_items=50
    )
    group_ids: Optional[List[str]] = Field(
        default=None,
        description="List of group IDs to grant permission to",
        max_items=50
    )
    group_names: Optional[List[str]] = Field(
        default=None,
        description="List of group names to grant permission to (alternative to group_ids)",
        max_items=50
    )

    @field_validator('user_account_ids', 'group_ids')
    @classmethod
    def check_at_least_one(cls, v: Optional[List[str]], info) -> Optional[List[str]]:
        """Ensure at least one of user_account_ids or group_ids is provided."""
        # This validator runs for each field, so we can't check both here
        # We'll validate in the tool function instead
        return v


class GetRestrictionsInput(BaseModel):
    """Input for getting page restrictions."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    page_id: str = Field(
        ...,
        description="ID of the page to get restrictions for",
        min_length=1
    )


class RemoveRestrictionInput(BaseModel):
    """Input for removing restrictions from a page."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    page_id: Optional[str] = Field(
        default=None,
        description="ID of the page to remove restrictions from",
        min_length=1
    )
    page_title: Optional[str] = Field(
        default=None,
        description="Title of the page to remove restrictions from (alternative to page_id)",
        min_length=1
    )
    space_key: Optional[str] = Field(
        default=None,
        description="Space key (required when using page_title)",
        min_length=1
    )
    operation: Optional[OperationType] = Field(
        default=None,
        description="Type of restriction to remove: 'read' or 'update'. If not specified, removes ALL restrictions."
    )
    remove_all: bool = Field(
        default=False,
        description="If True, removes ALL restrictions (both read and update) from the page"
    )


class GetSpacePagesInput(BaseModel):
    """Input for getting pages in a space."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    space_key: str = Field(
        ...,
        description="Space key to search in (e.g., 'TEAM', 'DOCS')",
        min_length=1,
        max_length=255
    )
    title: Optional[str] = Field(
        default=None,
        description="Optional title filter to search for specific pages",
        min_length=1
    )
    limit: int = Field(
        default=25,
        description="Maximum number of results to return (default: 25, max: 100)",
        ge=1,
        le=100
    )
    start: int = Field(
        default=0,
        description="Starting index for pagination (default: 0)",
        ge=0
    )
    expand: Optional[str] = Field(
        default="version,space,history,body.storage",
        description="Comma-separated list of properties to expand (e.g., 'version,space,history,body.storage')"
    )


class GetChildPagesInput(BaseModel):
    """Input for getting child pages of a specific page."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    page_id: Optional[str] = Field(
        default=None,
        description="ID of the parent page to get children for",
        min_length=1
    )
    page_title: Optional[str] = Field(
        default=None,
        description="Title of the parent page (alternative to page_id)",
        min_length=1
    )
    space_key: Optional[str] = Field(
        default=None,
        description="Space key (required when using page_title)",
        min_length=1
    )
    limit: int = Field(
        default=25,
        description="Maximum number of results to return (default: 25, max: 100)",
        ge=1,
        le=100
    )
    start: int = Field(
        default=0,
        description="Starting index for pagination (default: 0)",
        ge=0
    )
    expand: Optional[str] = Field(
        default="version,space,history",
        description="Comma-separated list of properties to expand (e.g., 'version,space,history')"
    )


class SearchPagesInput(BaseModel):
    """Input for searching Confluence pages using CQL."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    query: str = Field(
        ...,
        description="Search query. Can be plain text or CQL expression (e.g., 'title ~ \"Meeting\" AND space = \"TEAM\"')",
        min_length=1
    )
    space_key: Optional[str] = Field(
        default=None,
        description="Optional space key to limit search to a specific space"
    )
    limit: int = Field(
        default=25,
        description="Maximum number of results to return (default: 25, max: 100)",
        ge=1,
        le=100
    )
    start: int = Field(
        default=0,
        description="Starting index for pagination (default: 0)",
        ge=0
    )


class GetPageInput(BaseModel):
    """Input for reading a specific Confluence page."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    page_id: Optional[str] = Field(
        default=None,
        description="ID of the page to read",
        min_length=1
    )
    page_title: Optional[str] = Field(
        default=None,
        description="Title of the page to read (alternative to page_id)",
        min_length=1
    )
    space_key: Optional[str] = Field(
        default=None,
        description="Space key (required when using page_title)"
    )
    include_content: bool = Field(
        default=True,
        description="Whether to include the full page content (default: True)"
    )
    convert_to_markdown: bool = Field(
        default=True,
        description="Convert page content from HTML/storage to Markdown (default: True). Set to False to get raw HTML."
    )


class SyncUserDirectoryInput(BaseModel):
    """Input for syncing user directory in Confluence."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    directory_id: Optional[str] = Field(
        default=None,
        description="Directory ID to sync. If not provided, uses CONFLUENCE_DIRECTORY_ID env variable."
    )
    login: Optional[str] = Field(
        default=None,
        description="Admin login for Confluence. If not provided, uses CONFLUENCE_LOGIN env variable."
    )
    password: Optional[str] = Field(
        default=None,
        description="Admin password for Confluence. If not provided, uses CONFLUENCE_LOGIN_PASSWORD env variable."
    )


class UpdatePageInput(BaseModel):
    """Input for updating a Confluence page (title and/or content)."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )

    page_id: Optional[str] = Field(
        default=None,
        description="ID of the page to update",
        min_length=1
    )
    page_title: Optional[str] = Field(
        default=None,
        description="Current title of the page to update (alternative to page_id)",
        min_length=1
    )
    space_key: Optional[str] = Field(
        default=None,
        description="Space key (required when using page_title)",
        min_length=1
    )
    new_title: Optional[str] = Field(
        default=None,
        description="New title for the page. If not provided, the title stays unchanged.",
        min_length=1,
        max_length=255
    )
    new_content: Optional[str] = Field(
        default=None,
        description="New content for the page. If not provided, the content stays unchanged.",
        min_length=1
    )
    content_format: Literal["storage", "markdown", "wiki"] = Field(
        default="storage",
        description="Input format of new_content: 'storage' (raw HTML, default), 'markdown', or 'wiki'"
    )
    version_message: Optional[str] = Field(
        default=None,
        description="Optional version comment describing the change",
        max_length=500
    )


class DeletePageInput(BaseModel):
    """Input for deleting a Confluence page."""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    page_id: Optional[str] = Field(default=None, description="ID of the page to delete", min_length=1)
    page_title: Optional[str] = Field(default=None, description="Title of the page to delete (alternative to page_id)", min_length=1)
    space_key: Optional[str] = Field(default=None, description="Space key (required when using page_title)", min_length=1)


class GetCommentsInput(BaseModel):
    """Input for getting comments on a Confluence page."""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    page_id: str = Field(..., description="ID of the page to get comments for", min_length=1)
    limit: int = Field(default=25, description="Maximum number of comments to return (max: 50)", ge=1, le=50)
    convert_to_markdown: bool = Field(default=True, description="Convert comment body from HTML to Markdown (default: True)")


class AddCommentInput(BaseModel):
    """Input for adding a comment to a Confluence page."""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    page_id: str = Field(..., description="ID of the page to comment on", min_length=1)
    content: str = Field(..., description="Comment text in Markdown format", min_length=1)


class GetLabelsInput(BaseModel):
    """Input for getting labels on a Confluence page."""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    page_id: str = Field(..., description="ID of the page to get labels for", min_length=1)


class AddLabelInput(BaseModel):
    """Input for adding a label to a Confluence page."""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    page_id: str = Field(..., description="ID of the page to add a label to", min_length=1)
    name: str = Field(..., description="Label name (lowercase, spaces replaced with hyphens)", min_length=1, max_length=255)


class SearchUserInput(BaseModel):
    """Input for searching Confluence users."""
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra='forbid')

    query: str = Field(..., description="Search query — plain text (e.g. 'Jan Novak') or CQL expression", min_length=1)
    group_name: Optional[str] = Field(default=None, description="Optional group name to search members within (DC fallback)")
    limit: int = Field(default=10, description="Maximum number of results to return", ge=1, le=50)


async def _find_page_by_title(client: httpx.AsyncClient, space_key: str, title: str) -> Optional[str]:
    """Find page ID by title in a specific space.

    Args:
        client: HTTP client
        space_key: Space key to search in
        title: Page title to search for

    Returns:
        Page ID if found, None otherwise
    """
    try:
        response = await client.get(
            "/rest/api/content",
            params={
                "spaceKey": space_key,
                "title": title,
                "type": "page",
                "limit": 1
            }
        )
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])
        if results:
            return results[0]["id"]
        return None
    except Exception:
        return None


async def _find_group_by_name(client: httpx.AsyncClient, group_name: str) -> Optional[str]:
    """Find group ID by group name.

    Args:
        client: HTTP client
        group_name: Group name to search for

    Returns:
        Group name (used as ID in on-premise Confluence)

    Note:
        On-premise Confluence uses group names directly as IDs in the legacy API.
        We return the group name without verification, similar to how the PowerShell
        script works. The API will validate the group when setting permissions.
    """
    # In on-premise Confluence with legacy API, group name IS the ID
    # We don't need to verify existence - the API will do that when setting permissions
    return group_name


async def _find_user_by_identifier(client: httpx.AsyncClient, identifier: str) -> Optional[str]:
    """Find user account ID by email or username.

    Args:
        client: HTTP client
        identifier: Email address or username

    Returns:
        Account ID if found, None otherwise
    """
    try:
        # Try by username first
        response = await client.get(
            "/rest/api/user",
            params={"username": identifier}
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("accountId")

        # If not found, try searching by email or display name
        response = await client.get(
            "/rest/api/search/user",
            params={"query": identifier}
        )
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            if results:
                return results[0].get("accountId")

        return None
    except Exception:
        return None


def _html_to_markdown(html: str) -> str:
    """Convert HTML/storage content to Markdown."""
    if not html:
        return ""
    if _HTML2TEXT_AVAILABLE:
        h = _html2text_module.HTML2Text()
        h.ignore_links = False
        h.ignore_images = False
        h.body_width = 0
        return h.handle(html).strip()
    # Fallback: strip HTML tags
    return re.sub(r'<[^>]+>', '', html).strip()


def _markdown_to_storage(md: str) -> str:
    """Convert Markdown to Confluence storage (HTML) format."""
    if not md:
        return ""
    if _MARKDOWN_AVAILABLE:
        return _markdown_module.markdown(
            md,
            extensions=["tables", "fenced_code", "nl2br"]
        )
    # Fallback: wrap as plain text paragraphs
    return "".join(f"<p>{line}</p>" for line in md.split("\n") if line.strip())


def _prepare_content_html(content: str, content_format: str = "storage") -> str:
    """Prepare content for Confluence storage format."""
    if content_format == "markdown":
        return _markdown_to_storage(content)
    if content_format == "wiki":
        # Wiki markup passed through as-is (server-side rendering handles it)
        return content
    # storage / auto-detect
    if not any(tag in content.lower() for tag in ['<p>', '<h1>', '<h2>', '<h3>', '<div>', '<table>']):
        return f"<p>{content}</p>"
    return content


@mcp.tool(
    name="confluence_create_page",
    annotations={
        "title": "Create Confluence Page",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True
    }
)
async def create_page(params: CreatePageInput) -> str:
    """Create a new Confluence page with specified content.

    This tool creates a new page in a Confluence space with the provided content.
    The content can be plain text or HTML. If plain text is provided, it will be
    automatically wrapped in paragraph tags.

    Args:
        params (CreatePageInput): Page creation parameters containing:
            - space_key (str): Space key where page will be created
            - title (str): Page title
            - content (str): Page content (plain text or HTML)
            - parent_id (Optional[str]): Parent page ID for nested pages
            - editor_version (EditorVersion): Editor version (v1 or v2)

    Returns:
        str: JSON response containing:
            - success (bool): Whether creation succeeded
            - page_id (str): ID of the created page
            - page_url (str): URL to view the page
            - title (str): Page title
            - space_key (str): Space key
    """
    try:
        client = get_http_client()

        # Validate parent parameters
        if params.parent_id and params.parent_title:
            return json.dumps({
                "success": False,
                "error": "Cannot specify both parent_id and parent_title. Please use only one."
            }, indent=2)

        # Resolve parent_title to parent_id if needed
        parent_id = params.parent_id
        if params.parent_title:
            parent_id = await _find_page_by_title(client, params.space_key, params.parent_title)
            if not parent_id:
                return json.dumps({
                    "success": False,
                    "error": f"Parent page with title '{params.parent_title}' not found in space '{params.space_key}'"
                }, indent=2)

        # Prepare content
        html_content = _prepare_content_html(params.content, params.content_format)

        # Build request payload
        payload: dict = {
            "type": "page",
            "title": params.title,
            "space": {"key": params.space_key},
            "body": {
                "storage": {
                    "value": html_content,
                    "representation": "storage"
                }
            }
        }

        # Add parent if specified
        if parent_id:
            payload["ancestors"] = [{"id": parent_id}]

        # Add editor version metadata for v2
        if params.editor_version == EditorVersion.V2:
            payload["metadata"] = {
                "properties": {
                    "editor": {"value": "v2"}
                }
            }

        # Create the page
        response = await client.post(
            "/rest/api/content",
            json=payload
        )
        response.raise_for_status()

        data = response.json()
        page_id = data["id"]

        # Construct page URL
        page_url = f"{CONFLUENCE_URL}/pages/viewpage.action?pageId={page_id}"

        result = {
            "success": True,
            "page_id": page_id,
            "page_url": page_url,
            "title": params.title,
            "space_key": params.space_key,
            "message": f"Page '{params.title}' created successfully"
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        error_msg = _handle_api_error(e)
        return json.dumps({
            "success": False,
            "error": error_msg
        }, indent=2)


@mcp.tool(
    name="confluence_update_page",
    annotations={
        "title": "Update Confluence Page",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True
    }
)
async def update_page(params: UpdatePageInput) -> str:
    """Update an existing Confluence page's title and/or content.

    This tool updates an existing page. You can rename the page by providing
    new_title, replace its content by providing new_content, or do both at once.
    The page can be identified either by page_id or by page_title + space_key.

    The Confluence REST API requires the full page payload (title, type, body,
    incremented version) for any update, so the current values are fetched first
    and any field you don't override is preserved as-is.

    Args:
        params (UpdatePageInput): Update parameters containing:
            - page_id (Optional[str]): ID of the page to update
            - page_title (Optional[str]): Current title (alternative to page_id)
            - space_key (Optional[str]): Space key (required when using page_title)
            - new_title (Optional[str]): New title (if renaming)
            - new_content (Optional[str]): New content (if changing body)
            - version_message (Optional[str]): Optional change comment

    Returns:
        str: JSON response containing:
            - success (bool): Whether the update succeeded
            - page_id (str): Page ID
            - page_url (str): URL to view the page
            - old_title (str): Title before the update
            - new_title (str): Title after the update
            - title_changed (bool): Whether the title was changed
            - content_changed (bool): Whether the content was changed
            - new_version (int): New version number
            - space_key (str): Space key
    """
    try:
        client = get_http_client()

        # Validate page parameters
        if params.page_id and params.page_title:
            return json.dumps({
                "success": False,
                "error": "Cannot specify both page_id and page_title. Please use only one."
            }, indent=2)

        if not params.page_id and not params.page_title:
            return json.dumps({
                "success": False,
                "error": "Must specify either page_id or page_title."
            }, indent=2)

        # Must update at least something
        if not params.new_title and not params.new_content:
            return json.dumps({
                "success": False,
                "error": "Must specify at least one of new_title or new_content."
            }, indent=2)

        # Resolve page_title -> page_id
        page_id = params.page_id
        if params.page_title:
            if not params.space_key:
                return json.dumps({
                    "success": False,
                    "error": "space_key is required when using page_title"
                }, indent=2)
            page_id = await _find_page_by_title(client, params.space_key, params.page_title)
            if not page_id:
                return json.dumps({
                    "success": False,
                    "error": f"Page with title '{params.page_title}' not found in space '{params.space_key}'"
                }, indent=2)

        # Fetch current page state (version, space, and body if we are not replacing it)
        expand_parts = ["version", "space"]
        if not params.new_content:
            expand_parts.append("body.storage")

        current_resp = await client.get(
            f"/rest/api/content/{page_id}",
            params={"expand": ",".join(expand_parts)}
        )
        current_resp.raise_for_status()
        current_page = current_resp.json()

        current_version = current_page.get("version", {}).get("number", 1)
        current_title = current_page.get("title", "")
        space_key = current_page.get("space", {}).get("key", "")

        # Decide final values
        final_title = params.new_title if params.new_title else current_title

        if params.new_content:
            final_content = _prepare_content_html(params.new_content, params.content_format)
        else:
            final_content = current_page.get("body", {}).get("storage", {}).get("value", "")

        # Build update payload
        payload: dict = {
            "version": {
                "number": current_version + 1
            },
            "title": final_title,
            "type": "page",
            "body": {
                "storage": {
                    "value": final_content,
                    "representation": "storage"
                }
            }
        }

        if params.version_message:
            payload["version"]["message"] = params.version_message

        # Send update request
        response = await client.put(
            f"/rest/api/content/{page_id}",
            json=payload
        )
        response.raise_for_status()

        data = response.json()
        updated_page_id = data.get("id", page_id)
        page_url = f"{CONFLUENCE_URL}/pages/viewpage.action?pageId={updated_page_id}"

        result = {
            "success": True,
            "page_id": updated_page_id,
            "page_url": page_url,
            "old_title": current_title,
            "new_title": final_title,
            "title_changed": current_title != final_title,
            "content_changed": params.new_content is not None,
            "new_version": data.get("version", {}).get("number", current_version + 1),
            "space_key": space_key,
            "message": f"Page '{final_title}' updated successfully"
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        error_msg = _handle_api_error(e)
        return json.dumps({
            "success": False,
            "error": error_msg
        }, indent=2)


@mcp.tool(
    name="confluence_add_restrictions",
    annotations={
        "title": "Add Page Restrictions",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def add_restrictions(params: AddRestrictionInput) -> str:
    """Add read or edit restrictions to a Confluence page.

    This tool adds restrictions to control who can view (read) or edit (update)
    a Confluence page. You can specify users by their account IDs and/or groups
    by their group IDs.

    Note: At least one of user_account_ids or group_ids must be provided.

    Args:
        params (AddRestrictionInput): Restriction parameters containing:
            - page_id (str): ID of the page to restrict
            - operation (OperationType): 'read' or 'update'
            - user_account_ids (Optional[List[str]]): User account IDs
            - group_ids (Optional[List[str]]): Group IDs

    Returns:
        str: JSON response containing:
            - success (bool): Whether restrictions were added
            - page_id (str): Page ID
            - operation (str): Operation type
            - users_added (int): Number of users added
            - groups_added (int): Number of groups added
    """
    try:
        client = get_http_client()

        # Validate page parameters
        if params.page_id and params.page_title:
            return json.dumps({
                "success": False,
                "error": "Cannot specify both page_id and page_title. Please use only one."
            }, indent=2)

        if not params.page_id and not params.page_title:
            return json.dumps({
                "success": False,
                "error": "Must specify either page_id or page_title."
            }, indent=2)

        # Resolve page_title to page_id if needed and get page title
        page_id = params.page_id
        page_title = params.page_title

        if params.page_title:
            if not params.space_key:
                return json.dumps({
                    "success": False,
                    "error": "space_key is required when using page_title"
                }, indent=2)

            page_id = await _find_page_by_title(client, params.space_key, params.page_title)
            if not page_id:
                return json.dumps({
                    "success": False,
                    "error": f"Page with title '{params.page_title}' not found in space '{params.space_key}'"
                }, indent=2)
        else:
            # If we only have page_id, fetch the page title
            try:
                response = await client.get(f"/rest/api/content/{page_id}")
                response.raise_for_status()
                page_data = response.json()
                page_title = page_data.get("title", "")
            except Exception:
                page_title = ""

        # Collect all user account IDs (from IDs and identifiers)
        user_account_ids = list(params.user_account_ids or [])

        # Resolve user identifiers to account IDs
        if params.user_identifiers:
            for identifier in params.user_identifiers:
                account_id = await _find_user_by_identifier(client, identifier)
                if account_id:
                    user_account_ids.append(account_id)
                else:
                    return json.dumps({
                        "success": False,
                        "error": f"User '{identifier}' not found"
                    }, indent=2)

        # Collect all group IDs (from IDs and names)
        group_ids = list(params.group_ids or [])

        # Resolve group names to IDs
        if params.group_names:
            for group_name in params.group_names:
                group_id = await _find_group_by_name(client, group_name)
                if group_id:
                    group_ids.append(group_id)
                else:
                    return json.dumps({
                        "success": False,
                        "error": f"Group '{group_name}' not found"
                    }, indent=2)

        # Validate at least one restriction type is provided
        if not user_account_ids and not group_ids:
            return json.dumps({
                "success": False,
                "error": "At least one user or group must be specified"
            }, indent=2)

        # Check if page name contains "Private" or "Shared"
        # These pages get "Viewing and editing restricted" (both view + edit)
        # Other pages get "Editing restricted" (only edit, everyone can view)
        is_private_or_shared = "Private" in page_title or "Shared" in page_title

        # Use legacy Confluence API for setting permissions (works with on-premise)
        # This API uses form data instead of JSON
        form_data = []

        # Add user permissions
        for account_id in user_account_ids:
            if params.operation.value == "read":
                # Read only - just view permission
                form_data.append(f"viewPermissionsUserList={account_id}")
            elif params.operation.value == "update":
                # Edit permission
                if is_private_or_shared:
                    # Private/Shared pages: BOTH view and edit (Viewing and editing restricted)
                    form_data.append(f"viewPermissionsUserList={account_id}")
                    form_data.append(f"editPermissionsUserList={account_id}")
                else:
                    # Regular pages: only edit (Editing restricted - everyone can view)
                    form_data.append(f"editPermissionsUserList={account_id}")

        # Add group permissions
        for group_id in group_ids:
            if params.operation.value == "read":
                # Read only - just view permission
                form_data.append(f"viewPermissionsGroupList={group_id}")
            elif params.operation.value == "update":
                # Edit permission
                if is_private_or_shared:
                    # Private/Shared pages: BOTH view and edit (Viewing and editing restricted)
                    form_data.append(f"viewPermissionsGroupList={group_id}")
                    form_data.append(f"editPermissionsGroupList={group_id}")
                else:
                    # Regular pages: only edit (Editing restricted - everyone can view)
                    form_data.append(f"editPermissionsGroupList={group_id}")

        # Add page ID
        form_data.append(f"contentId={page_id}")

        # Join with &
        form_body = "&".join(form_data)

        try:
            # Use legacy endpoint with form data
            response = await client.post(
                "/pages/setcontentpermissions.action",
                content=form_body,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-Atlassian-Token": "no-check"
                }
            )
            response.raise_for_status()

            # Check if response contains "true" (success indicator)
            if "true" in response.text.lower():
                users_added = len(user_account_ids)
                groups_added = len(group_ids)
                errors = []
            else:
                users_added = 0
                groups_added = 0
                errors = [f"API returned unexpected response: {response.text[:200]}"]
        except Exception as e:
            users_added = 0
            groups_added = 0
            errors = [_handle_api_error(e)]

        result = {
            "success": users_added > 0 or groups_added > 0,
            "page_id": page_id,
            "operation": params.operation.value,
            "users_added": users_added,
            "groups_added": groups_added
        }

        if errors:
            result["warnings"] = errors

        if users_added > 0 or groups_added > 0:
            result["message"] = f"Added {params.operation.value} restrictions: {users_added} users, {groups_added} groups"
        else:
            result["message"] = "No restrictions were added"

        return json.dumps(result, indent=2)

    except Exception as e:
        error_msg = _handle_api_error(e)
        return json.dumps({
            "success": False,
            "error": error_msg
        }, indent=2)


@mcp.tool(
    name="confluence_get_restrictions",
    annotations={
        "title": "Get Page Restrictions",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def get_restrictions(params: GetRestrictionsInput) -> str:
    """Get current restrictions for a Confluence page.

    This tool retrieves all read and edit restrictions currently applied to a page,
    including which users and groups have access.

    Args:
        params (GetRestrictionsInput): Parameters containing:
            - page_id (str): ID of the page to get restrictions for

    Returns:
        str: JSON response containing:
            - success (bool): Whether retrieval succeeded
            - page_id (str): Page ID
            - restrictions (dict): Restrictions by operation type with users and groups
    """
    try:
        client = get_http_client()

        # Get restrictions with expand parameter
        response = await client.get(
            f"/rest/api/content/{params.page_id}/restriction/byOperation",
            params={
                "expand": "read.restrictions.user,read.restrictions.group,update.restrictions.user,update.restrictions.group"
            }
        )
        response.raise_for_status()

        data = response.json()

        # Parse restrictions
        restrictions = {}

        for operation in ["read", "update"]:
            if operation in data:
                op_data = data[operation]
                restrictions[operation] = {
                    "users": [],
                    "groups": []
                }

                # Parse users
                if "restrictions" in op_data and "user" in op_data["restrictions"]:
                    user_results = op_data["restrictions"]["user"].get("results", [])
                    for user in user_results:
                        restrictions[operation]["users"].append({
                            "accountId": user.get("accountId"),
                            "displayName": user.get("displayName", user.get("publicName", "Unknown")),
                            "email": user.get("email", "N/A")
                        })

                # Parse groups
                if "restrictions" in op_data and "group" in op_data["restrictions"]:
                    group_results = op_data["restrictions"]["group"].get("results", [])
                    for group in group_results:
                        restrictions[operation]["groups"].append({
                            "id": group.get("id"),
                            "name": group.get("name", "Unknown")
                        })

        result = {
            "success": True,
            "page_id": params.page_id,
            "restrictions": restrictions
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        error_msg = _handle_api_error(e)
        return json.dumps({
            "success": False,
            "error": error_msg
        }, indent=2)


@mcp.tool(
    name="confluence_remove_restrictions",
    annotations={
        "title": "Remove Page Restrictions",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def remove_restrictions(params: RemoveRestrictionInput) -> str:
    """Remove restrictions from a Confluence page.

    This tool removes read and/or edit restrictions from a page. You can either:
    - Remove ALL restrictions (set remove_all=True)
    - Remove restrictions for a specific operation (specify 'read' or 'update')

    Args:
        params (RemoveRestrictionInput): Parameters containing:
            - page_id (str): ID of the page to remove restrictions from
            - page_title (str): Title of the page (alternative to page_id)
            - space_key (str): Space key (required when using page_title)
            - operation (Optional[OperationType]): 'read' or 'update' to remove specific restriction
            - remove_all (bool): If True, removes ALL restrictions

    Returns:
        str: JSON response containing:
            - success (bool): Whether restrictions were removed
            - page_id (str): Page ID
            - removed_operations (list): List of operations that had restrictions removed
    """
    try:
        client = get_http_client()

        # Validate page parameters
        if params.page_id and params.page_title:
            return json.dumps({
                "success": False,
                "error": "Cannot specify both page_id and page_title. Please use only one."
            }, indent=2)

        if not params.page_id and not params.page_title:
            return json.dumps({
                "success": False,
                "error": "Must specify either page_id or page_title."
            }, indent=2)

        # Resolve page_title to page_id if needed
        page_id = params.page_id
        page_title = params.page_title

        if params.page_title:
            if not params.space_key:
                return json.dumps({
                    "success": False,
                    "error": "space_key is required when using page_title"
                }, indent=2)

            page_id = await _find_page_by_title(client, params.space_key, params.page_title)
            if not page_id:
                return json.dumps({
                    "success": False,
                    "error": f"Page with title '{params.page_title}' not found in space '{params.space_key}'"
                }, indent=2)
        else:
            # If we only have page_id, fetch the page title
            try:
                response = await client.get(f"/rest/api/content/{page_id}")
                response.raise_for_status()
                page_data = response.json()
                page_title = page_data.get("title", "")
            except Exception:
                page_title = ""

        # Determine which operations to remove
        operations_to_remove = []
        if params.remove_all or params.operation is None:
            operations_to_remove = ["read", "update"]
        elif params.operation:
            operations_to_remove = [params.operation.value]

        # Remove restrictions for each operation
        removed_operations = []
        errors = []

        for operation in operations_to_remove:
            try:
                # Use REST API to delete restrictions
                response = await client.delete(
                    f"/rest/api/content/{page_id}/restriction/byOperation/{operation}"
                )

                # Accept both 204 (No Content - success) and 404 (Not Found - no restrictions to remove)
                if response.status_code in [204, 404]:
                    removed_operations.append(operation)
                else:
                    response.raise_for_status()
                    removed_operations.append(operation)

            except httpx.HTTPStatusError as e:
                # If 404, it means there were no restrictions - that's okay
                if e.response.status_code == 404:
                    removed_operations.append(operation)
                else:
                    errors.append(f"Failed to remove {operation} restrictions: {_handle_api_error(e)}")
            except Exception as e:
                errors.append(f"Failed to remove {operation} restrictions: {_handle_api_error(e)}")

        result = {
            "success": len(removed_operations) > 0,
            "page_id": page_id,
            "page_title": page_title,
            "removed_operations": removed_operations
        }

        if errors:
            result["warnings"] = errors

        if removed_operations:
            result["message"] = f"Removed restrictions for: {', '.join(removed_operations)}"
        else:
            result["message"] = "No restrictions were removed"

        return json.dumps(result, indent=2)

    except Exception as e:
        error_msg = _handle_api_error(e)
        return json.dumps({
            "success": False,
            "error": error_msg
        }, indent=2)


@mcp.tool(
    name="confluence_get_space_pages",
    annotations={
        "title": "Get Pages in Space",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def get_space_pages(params: GetSpacePagesInput) -> str:
    """Get all pages in a Confluence space with optional filtering.

    This tool retrieves pages from a specific space. You can optionally filter
    by title and control pagination. The response includes page details like
    ID, title, URL, version, and content.

    Args:
        params (GetSpacePagesInput): Parameters containing:
            - space_key (str): Space key to search in (required)
            - title (Optional[str]): Title filter for searching specific pages
            - limit (int): Maximum results to return (default: 25, max: 100)
            - start (int): Starting index for pagination (default: 0)
            - expand (Optional[str]): Properties to expand (default: version,space,history,body.storage)

    Returns:
        str: JSON response containing:
            - success (bool): Whether retrieval succeeded
            - space_key (str): Space key
            - total_count (int): Total number of pages found
            - returned_count (int): Number of pages in this response
            - start (int): Starting index
            - limit (int): Limit used
            - pages (list): List of page objects with details
    """
    try:
        client = get_http_client()

        # Build query parameters
        query_params = {
            "spaceKey": params.space_key,
            "type": "page",
            "limit": params.limit,
            "start": params.start
        }

        # Add title filter if provided
        if params.title:
            query_params["title"] = params.title

        # Add expand parameter if provided
        if params.expand:
            query_params["expand"] = params.expand

        # Make API request
        response = await client.get(
            "/rest/api/content",
            params=query_params
        )
        response.raise_for_status()

        data = response.json()

        # Parse results
        pages = []
        for page in data.get("results", []):
            page_info = {
                "id": page.get("id"),
                "title": page.get("title"),
                "type": page.get("type"),
                "status": page.get("status")
            }

            # Add URL
            if "_links" in page and "webui" in page["_links"]:
                page_info["url"] = f"{CONFLUENCE_URL}{page['_links']['webui']}"
            else:
                page_info["url"] = f"{CONFLUENCE_URL}/pages/viewpage.action?pageId={page.get('id')}"

            # Add version info if expanded
            if "version" in page:
                page_info["version"] = {
                    "number": page["version"].get("number"),
                    "when": page["version"].get("when"),
                    "by": page["version"].get("by", {}).get("displayName", "Unknown")
                }

            # Add space info if expanded
            if "space" in page:
                page_info["space"] = {
                    "key": page["space"].get("key"),
                    "name": page["space"].get("name")
                }

            # Add history info if expanded
            if "history" in page:
                page_info["created_date"] = page["history"].get("createdDate")
                page_info["created_by"] = page["history"].get("createdBy", {}).get("displayName", "Unknown")

            # Add content preview if body.storage is expanded
            if "body" in page and "storage" in page["body"]:
                content = page["body"]["storage"].get("value", "")
                # Provide first 200 characters as preview
                page_info["content_preview"] = content[:200] + ("..." if len(content) > 200 else "")
                page_info["content_length"] = len(content)

            pages.append(page_info)

        result = {
            "success": True,
            "space_key": params.space_key,
            "total_count": data.get("size", 0),
            "returned_count": len(pages),
            "start": params.start,
            "limit": params.limit,
            "pages": pages
        }

        # Add pagination info
        if "next" in data.get("_links", {}):
            result["has_more"] = True
            result["next_start"] = params.start + params.limit
        else:
            result["has_more"] = False

        return json.dumps(result, indent=2)

    except Exception as e:
        error_msg = _handle_api_error(e)
        return json.dumps({
            "success": False,
            "error": error_msg
        }, indent=2)


@mcp.tool(
    name="confluence_get_child_pages",
    annotations={
        "title": "Get Child Pages",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def get_child_pages(params: GetChildPagesInput) -> str:
    """Get all child pages of a specific parent page in Confluence.

    This tool retrieves all child pages (sub-pages) of a given parent page.
    You can specify the parent page by either page_id or page_title + space_key.

    Args:
        params (GetChildPagesInput): Parameters containing:
            - page_id (Optional[str]): ID of the parent page
            - page_title (Optional[str]): Title of the parent page (alternative to page_id)
            - space_key (Optional[str]): Space key (required when using page_title)
            - limit (int): Maximum results to return (default: 25, max: 100)
            - start (int): Starting index for pagination (default: 0)
            - expand (Optional[str]): Properties to expand (default: version,space,history)

    Returns:
        str: JSON response containing:
            - success (bool): Whether retrieval succeeded
            - parent_page_id (str): Parent page ID
            - parent_page_title (str): Parent page title
            - total_count (int): Total number of child pages
            - returned_count (int): Number of pages in this response
            - start (int): Starting index
            - limit (int): Limit used
            - child_pages (list): List of child page objects with details
    """
    try:
        client = get_http_client()

        # Validate page parameters
        if params.page_id and params.page_title:
            return json.dumps({
                "success": False,
                "error": "Cannot specify both page_id and page_title. Please use only one."
            }, indent=2)

        if not params.page_id and not params.page_title:
            return json.dumps({
                "success": False,
                "error": "Must specify either page_id or page_title."
            }, indent=2)

        # Resolve page_title to page_id if needed
        page_id = params.page_id
        parent_page_title = params.page_title

        if params.page_title:
            if not params.space_key:
                return json.dumps({
                    "success": False,
                    "error": "space_key is required when using page_title"
                }, indent=2)

            page_id = await _find_page_by_title(client, params.space_key, params.page_title)
            if not page_id:
                return json.dumps({
                    "success": False,
                    "error": f"Page with title '{params.page_title}' not found in space '{params.space_key}'"
                }, indent=2)
        else:
            # If we only have page_id, fetch the page title
            try:
                response = await client.get(f"/rest/api/content/{page_id}")
                response.raise_for_status()
                page_data = response.json()
                parent_page_title = page_data.get("title", "")
            except Exception:
                parent_page_title = ""

        # Build query parameters for child pages
        query_params = {
            "limit": params.limit,
            "start": params.start
        }

        # Add expand parameter if provided
        if params.expand:
            query_params["expand"] = params.expand

        # Make API request to get child pages
        response = await client.get(
            f"/rest/api/content/{page_id}/child/page",
            params=query_params
        )
        response.raise_for_status()

        data = response.json()

        # Parse results
        child_pages = []
        for page in data.get("results", []):
            page_info = {
                "id": page.get("id"),
                "title": page.get("title"),
                "type": page.get("type"),
                "status": page.get("status")
            }

            # Add URL
            if "_links" in page and "webui" in page["_links"]:
                page_info["url"] = f"{CONFLUENCE_URL}{page['_links']['webui']}"
            else:
                page_info["url"] = f"{CONFLUENCE_URL}/pages/viewpage.action?pageId={page.get('id')}"

            # Add version info if expanded
            if "version" in page:
                page_info["version"] = {
                    "number": page["version"].get("number"),
                    "when": page["version"].get("when"),
                    "by": page["version"].get("by", {}).get("displayName", "Unknown")
                }

            # Add space info if expanded
            if "space" in page:
                page_info["space"] = {
                    "key": page["space"].get("key"),
                    "name": page["space"].get("name")
                }

            # Add history info if expanded
            if "history" in page:
                page_info["created_date"] = page["history"].get("createdDate")
                page_info["created_by"] = page["history"].get("createdBy", {}).get("displayName", "Unknown")

            child_pages.append(page_info)

        result = {
            "success": True,
            "parent_page_id": page_id,
            "parent_page_title": parent_page_title,
            "total_count": data.get("size", 0),
            "returned_count": len(child_pages),
            "start": params.start,
            "limit": params.limit,
            "child_pages": child_pages
        }

        # Add pagination info
        if "next" in data.get("_links", {}):
            result["has_more"] = True
            result["next_start"] = params.start + params.limit
        else:
            result["has_more"] = False

        return json.dumps(result, indent=2)

    except Exception as e:
        error_msg = _handle_api_error(e)
        return json.dumps({
            "success": False,
            "error": error_msg
        }, indent=2)


@mcp.tool(
    name="confluence_sync_user_directory",
    annotations={
        "title": "Sync User Directory",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def sync_user_directory(params: SyncUserDirectoryInput) -> str:
    """Synchronize Confluence user directory with external directory (e.g., Active Directory).

    This tool triggers a sync of the configured user directory in Confluence.
    It requires admin credentials with access to user directory management.

    The sync process:
    1. Logs into Confluence with admin credentials
    2. Authenticates to user directory management
    3. Extracts ATL token from session
    4. Triggers directory synchronization

    Args:
        params (SyncUserDirectoryInput): Sync parameters containing:
            - directory_id (Optional[str]): Directory ID to sync (default from env)
            - login (Optional[str]): Admin login (default from env)
            - password (Optional[str]): Admin password (default from env)

    Returns:
        str: JSON response containing:
            - success (bool): Whether sync was triggered successfully
            - message (str): Status message
            - directory_id (str): ID of the synced directory
    """
    try:
        # Get credentials from params or environment
        login = params.login or CONFLUENCE_LOGIN
        password = params.password or CONFLUENCE_LOGIN_PASSWORD
        directory_id = params.directory_id or CONFLUENCE_DIRECTORY_ID

        if not login or not password:
            return json.dumps({
                "success": False,
                "error": "Missing credentials. Set CONFLUENCE_LOGIN and CONFLUENCE_LOGIN_PASSWORD environment variables or provide them as parameters."
            }, indent=2)

        if not directory_id:
            return json.dumps({
                "success": False,
                "error": "Missing directory_id. Set CONFLUENCE_DIRECTORY_ID environment variable or provide it as parameter."
            }, indent=2)

        # Extract server URL from CONFLUENCE_URL
        server_url = CONFLUENCE_URL.replace("https://", "").replace("http://", "").rstrip("/")

        # Create a new client with cookies support for this session
        async with httpx.AsyncClient(
            base_url=f"https://{server_url}",
            timeout=60.0,
            follow_redirects=True
        ) as client:

            # Step 1: Login to Confluence
            login_body = {
                "username": login,
                "password": password,
                "rememberMe": True,
                "targetUrl": "",
                "captchaId": ""
            }

            try:
                login_response = await client.post(
                    "/rest/tsv/1.0/authenticate?os_authType=none",
                    json=login_body,
                    headers={"Content-Type": "application/json"}
                )
            except Exception as e:
                return json.dumps({
                    "success": False,
                    "error": f"Login failed: {str(e)}"
                }, indent=2)

            # Step 2: Authenticate to user directories
            auth_body = {
                "password": password,
                "authenticate": "Confirm",
                "destination": "/plugins/servlet/embedded-crowd/directories/list"
            }

            try:
                auth_response = await client.post(
                    "/doauthenticate.action",
                    data=auth_body,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "X-Atlassian-Token": "no-check"
                    }
                )
            except Exception as e:
                return json.dumps({
                    "success": False,
                    "error": f"Authentication to user directories failed: {str(e)}"
                }, indent=2)

            # Step 3: Extract ATL token from response
            atl_token = None
            try:
                # Search for atl_token in HTML response
                # Pattern: name="atl_token" value="..."
                match = re.search(r'name="atl_token"\s+value="([^"]+)"', auth_response.text)
                if match:
                    atl_token = match.group(1)
                else:
                    # Try alternative pattern
                    match = re.search(r'atl_token=([^&"\s]+)', auth_response.text)
                    if match:
                        atl_token = match.group(1)
            except Exception as e:
                return json.dumps({
                    "success": False,
                    "error": f"Failed to parse ATL token: {str(e)}"
                }, indent=2)

            if not atl_token:
                return json.dumps({
                    "success": False,
                    "error": "ATL_TOKEN not found in response. Authentication may have failed or user lacks admin permissions."
                }, indent=2)

            # Step 4: Trigger directory sync
            try:
                sync_response = await client.post(
                    f"/plugins/servlet/embedded-crowd/directories/sync?directoryId={directory_id}&atl_token={atl_token}",
                    headers={
                        "X-Atlassian-Token": "no-check"
                    }
                )

                # Check response
                if sync_response.status_code in [200, 302]:
                    return json.dumps({
                        "success": True,
                        "message": f"User directory sync triggered successfully for directory ID: {directory_id}",
                        "directory_id": directory_id
                    }, indent=2)
                else:
                    return json.dumps({
                        "success": False,
                        "error": f"Sync request returned status {sync_response.status_code}: {sync_response.text[:200]}"
                    }, indent=2)

            except Exception as e:
                return json.dumps({
                    "success": False,
                    "error": f"Failed to trigger sync: {str(e)}"
                }, indent=2)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }, indent=2)


@mcp.tool(
    name="confluence_search_pages",
    annotations={
        "title": "Search Confluence Pages",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def search_pages(params: SearchPagesInput) -> str:
    """Search Confluence pages using CQL or plain text query.

    This tool searches across Confluence pages using the Confluence Query Language (CQL).
    You can search by plain text or provide a full CQL expression for advanced filtering.

    Examples of CQL queries:
    - Plain text: "deployment guide"
    - Title search: 'title ~ "Meeting Notes"'
    - Space + text: 'space = "TEAM" AND text ~ "roadmap"'
    - Recent pages: 'space = "DOCS" AND lastmodified >= "2024-01-01"'

    Args:
        params (SearchPagesInput): Parameters containing:
            - query (str): Plain text or CQL query
            - space_key (Optional[str]): Limit search to a specific space
            - limit (int): Maximum results to return (default: 25, max: 100)
            - start (int): Starting index for pagination (default: 0)

    Returns:
        str: JSON response containing:
            - success (bool): Whether search succeeded
            - query (str): The CQL query used
            - total_count (int): Total number of matching pages
            - returned_count (int): Number of pages in this response
            - pages (list): List of page objects with id, title, space, url, excerpt
    """
    try:
        client = get_http_client()

        # Build CQL query
        # If query doesn't look like CQL (no operators/keywords), treat as full-text search
        cql_keywords = ["AND", "OR", "NOT", "~", "=", "!=", ">", "<", "IN ", "space ", "title ", "text ", "type ", "ancestor "]
        is_cql = any(kw in params.query for kw in cql_keywords)

        if is_cql:
            cql = params.query
        else:
            cql = f'text ~ "{params.query}" AND type = page'

        # Optionally restrict to a space
        if params.space_key and "space" not in cql:
            cql = f'space = "{params.space_key}" AND ({cql})'

        response = await client.get(
            "/rest/api/content/search",
            params={
                "cql": cql,
                "limit": params.limit,
                "start": params.start,
                "expand": "space,version,history"
            }
        )
        response.raise_for_status()

        data = response.json()

        pages = []
        for page in data.get("results", []):
            page_info = {
                "id": page.get("id"),
                "title": page.get("title"),
                "type": page.get("type"),
                "status": page.get("status")
            }

            if "_links" in page and "webui" in page["_links"]:
                page_info["url"] = f"{CONFLUENCE_URL}{page['_links']['webui']}"
            else:
                page_info["url"] = f"{CONFLUENCE_URL}/pages/viewpage.action?pageId={page.get('id')}"

            if "space" in page:
                page_info["space"] = {
                    "key": page["space"].get("key"),
                    "name": page["space"].get("name")
                }

            if "version" in page:
                page_info["last_modified"] = page["version"].get("when")
                page_info["last_modified_by"] = page["version"].get("by", {}).get("displayName", "Unknown")

            if "history" in page:
                page_info["created_date"] = page["history"].get("createdDate")
                page_info["created_by"] = page["history"].get("createdBy", {}).get("displayName", "Unknown")

            # Excerpt from search result
            if "excerpt" in page:
                page_info["excerpt"] = page["excerpt"]

            pages.append(page_info)

        result = {
            "success": True,
            "query": cql,
            "total_count": data.get("totalSize", data.get("size", 0)),
            "returned_count": len(pages),
            "start": params.start,
            "limit": params.limit,
            "pages": pages
        }

        if "next" in data.get("_links", {}):
            result["has_more"] = True
            result["next_start"] = params.start + params.limit
        else:
            result["has_more"] = False

        return json.dumps(result, indent=2)

    except Exception as e:
        error_msg = _handle_api_error(e)
        return json.dumps({
            "success": False,
            "error": error_msg
        }, indent=2)


@mcp.tool(
    name="confluence_get_page",
    annotations={
        "title": "Get Confluence Page",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def get_page(params: GetPageInput) -> str:
    """Read the full content of a specific Confluence page.

    This tool retrieves the complete details and content of a single Confluence page.
    You can identify the page by its ID or by title + space_key combination.

    Args:
        params (GetPageInput): Parameters containing:
            - page_id (Optional[str]): ID of the page to read
            - page_title (Optional[str]): Title of the page (alternative to page_id)
            - space_key (Optional[str]): Space key (required when using page_title)
            - include_content (bool): Whether to return full page content (default: True)

    Returns:
        str: JSON response containing:
            - success (bool): Whether retrieval succeeded
            - id (str): Page ID
            - title (str): Page title
            - space (dict): Space key and name
            - url (str): Page URL
            - version (dict): Version info (number, when, by)
            - created_date (str): Creation date
            - created_by (str): Creator display name
            - content (str): Full page content in HTML/storage format (if include_content=True)
            - content_length (int): Length of content in characters
    """
    try:
        client = get_http_client()

        # Validate parameters
        if params.page_id and params.page_title:
            return json.dumps({
                "success": False,
                "error": "Cannot specify both page_id and page_title. Please use only one."
            }, indent=2)

        if not params.page_id and not params.page_title:
            return json.dumps({
                "success": False,
                "error": "Must specify either page_id or page_title."
            }, indent=2)

        # Resolve page_title to page_id if needed
        page_id = params.page_id
        if params.page_title:
            if not params.space_key:
                return json.dumps({
                    "success": False,
                    "error": "space_key is required when using page_title"
                }, indent=2)
            page_id = await _find_page_by_title(client, params.space_key, params.page_title)
            if not page_id:
                return json.dumps({
                    "success": False,
                    "error": f"Page with title '{params.page_title}' not found in space '{params.space_key}'"
                }, indent=2)

        # Build expand parameter
        expand = "space,version,history"
        if params.include_content:
            expand += ",body.storage"

        response = await client.get(
            f"/rest/api/content/{page_id}",
            params={"expand": expand}
        )
        response.raise_for_status()

        page = response.json()

        result = {
            "success": True,
            "id": page.get("id"),
            "title": page.get("title"),
            "type": page.get("type"),
            "status": page.get("status")
        }

        if "_links" in page and "webui" in page["_links"]:
            result["url"] = f"{CONFLUENCE_URL}{page['_links']['webui']}"
        else:
            result["url"] = f"{CONFLUENCE_URL}/pages/viewpage.action?pageId={page.get('id')}"

        if "space" in page:
            result["space"] = {
                "key": page["space"].get("key"),
                "name": page["space"].get("name")
            }

        if "version" in page:
            result["version"] = {
                "number": page["version"].get("number"),
                "when": page["version"].get("when"),
                "by": page["version"].get("by", {}).get("displayName", "Unknown")
            }

        if "history" in page:
            result["created_date"] = page["history"].get("createdDate")
            result["created_by"] = page["history"].get("createdBy", {}).get("displayName", "Unknown")

        if params.include_content and "body" in page and "storage" in page["body"]:
            raw_content = page["body"]["storage"].get("value", "")
            if params.convert_to_markdown:
                content = _html_to_markdown(raw_content)
                result["content_format"] = "markdown"
            else:
                content = raw_content
                result["content_format"] = "storage"
            result["content"] = content
            result["content_length"] = len(content)

        return json.dumps(result, indent=2)

    except Exception as e:
        error_msg = _handle_api_error(e)
        return json.dumps({
            "success": False,
            "error": error_msg
        }, indent=2)


@mcp.tool(
    name="confluence_delete_page",
    annotations={
        "title": "Delete Confluence Page",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True
    }
)
async def delete_page(params: DeletePageInput) -> str:
    """Move a Confluence page to trash (soft delete).

    The page is moved to the Confluence trash and can be restored by an admin.
    This uses the standard REST API DELETE endpoint which performs a soft delete
    on both Confluence DC and Cloud.

    Args:
        params (DeletePageInput): Parameters containing:
            - page_id (Optional[str]): ID of the page to delete
            - page_title (Optional[str]): Title of the page (alternative to page_id)
            - space_key (Optional[str]): Space key (required when using page_title)

    Returns:
        str: JSON response containing:
            - success (bool): Whether deletion succeeded
            - page_id (str): ID of the deleted page
            - message (str): Status message
    """
    try:
        client = get_http_client()

        if params.page_id and params.page_title:
            return json.dumps({"success": False, "error": "Cannot specify both page_id and page_title."}, indent=2)
        if not params.page_id and not params.page_title:
            return json.dumps({"success": False, "error": "Must specify either page_id or page_title."}, indent=2)

        page_id = params.page_id
        if params.page_title:
            if not params.space_key:
                return json.dumps({"success": False, "error": "space_key is required when using page_title"}, indent=2)
            page_id = await _find_page_by_title(client, params.space_key, params.page_title)
            if not page_id:
                return json.dumps({"success": False, "error": f"Page '{params.page_title}' not found in space '{params.space_key}'"}, indent=2)

        response = await client.delete(f"/rest/api/content/{page_id}")

        if response.status_code in [200, 204]:
            return json.dumps({"success": True, "page_id": page_id, "message": "Page moved to trash."}, indent=2)
        response.raise_for_status()
        return json.dumps({"success": True, "page_id": page_id, "message": "Page moved to trash."}, indent=2)

    except Exception as e:
        return json.dumps({"success": False, "error": _handle_api_error(e)}, indent=2)


@mcp.tool(
    name="confluence_get_comments",
    annotations={
        "title": "Get Page Comments",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def get_comments(params: GetCommentsInput) -> str:
    """Get footer comments for a Confluence page.

    Retrieves all footer (inline comments are not supported by the DC REST API)
    comments for a page. Comment bodies are optionally converted to Markdown.

    Args:
        params (GetCommentsInput): Parameters containing:
            - page_id (str): ID of the page
            - limit (int): Max comments to return (default: 25, max: 50)
            - convert_to_markdown (bool): Convert body HTML to Markdown (default: True)

    Returns:
        str: JSON response containing:
            - page_id (str): Page ID
            - count (int): Number of comments returned
            - comments (list): List of {id, author, body, created}
    """
    try:
        client = get_http_client()

        response = await client.get(
            f"/rest/api/content/{params.page_id}/child/comment",
            params={
                "expand": "body.storage,version,history",
                "limit": params.limit
            }
        )
        response.raise_for_status()
        data = response.json()

        comments = []
        for item in data.get("results", []):
            body_html = item.get("body", {}).get("storage", {}).get("value", "")
            body = _html_to_markdown(body_html) if params.convert_to_markdown else body_html

            author = (
                item.get("history", {}).get("createdBy", {}).get("displayName")
                or item.get("version", {}).get("by", {}).get("displayName", "Unknown")
            )
            created = (
                item.get("history", {}).get("createdDate")
                or item.get("version", {}).get("when", "")
            )

            comments.append({
                "id": item.get("id"),
                "author": author,
                "body": body,
                "created": created
            })

        return json.dumps({
            "success": True,
            "page_id": params.page_id,
            "count": len(comments),
            "comments": comments
        }, indent=2)

    except Exception as e:
        return json.dumps({"success": False, "error": _handle_api_error(e)}, indent=2)


@mcp.tool(
    name="confluence_add_comment",
    annotations={
        "title": "Add Page Comment",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True
    }
)
async def add_comment(params: AddCommentInput) -> str:
    """Add a footer comment to a Confluence page.

    Accepts Markdown input and automatically converts it to Confluence storage
    format before posting. The comment will appear in the footer comments section.

    Args:
        params (AddCommentInput): Parameters containing:
            - page_id (str): ID of the page to comment on
            - content (str): Comment text in Markdown format

    Returns:
        str: JSON response containing:
            - success (bool): Whether the comment was added
            - comment_id (str): ID of the created comment
            - page_id (str): Page ID
            - created_at (str): Creation timestamp
    """
    try:
        client = get_http_client()

        storage_body = _markdown_to_storage(params.content)

        payload = {
            "type": "comment",
            "container": {"id": params.page_id, "type": "page"},
            "body": {
                "storage": {
                    "value": storage_body,
                    "representation": "storage"
                }
            }
        }

        response = await client.post("/rest/api/content", json=payload)
        response.raise_for_status()
        data = response.json()

        return json.dumps({
            "success": True,
            "comment_id": data.get("id"),
            "page_id": params.page_id,
            "created_at": data.get("version", {}).get("when", ""),
            "message": "Comment added successfully"
        }, indent=2)

    except Exception as e:
        return json.dumps({"success": False, "error": _handle_api_error(e)}, indent=2)


@mcp.tool(
    name="confluence_get_labels",
    annotations={
        "title": "Get Page Labels",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def get_labels(params: GetLabelsInput) -> str:
    """Get all labels assigned to a Confluence page.

    Args:
        params (GetLabelsInput): Parameters containing:
            - page_id (str): ID of the page

    Returns:
        str: JSON response containing:
            - page_id (str): Page ID
            - count (int): Number of labels
            - labels (list): List of {name, prefix, id}
    """
    try:
        client = get_http_client()

        response = await client.get(f"/rest/api/content/{params.page_id}/label")
        response.raise_for_status()
        data = response.json()

        labels = [
            {"name": lbl.get("name"), "prefix": lbl.get("prefix"), "id": lbl.get("id")}
            for lbl in data.get("results", [])
        ]

        return json.dumps({
            "success": True,
            "page_id": params.page_id,
            "count": len(labels),
            "labels": labels
        }, indent=2)

    except Exception as e:
        return json.dumps({"success": False, "error": _handle_api_error(e)}, indent=2)


@mcp.tool(
    name="confluence_add_label",
    annotations={
        "title": "Add Label to Page",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def add_label(params: AddLabelInput) -> str:
    """Add a label to a Confluence page.

    Adds a label with prefix 'global' (standard for DC). Adding a label that
    already exists is idempotent — no error is returned.

    Args:
        params (AddLabelInput): Parameters containing:
            - page_id (str): ID of the page
            - name (str): Label name (lowercase, spaces as hyphens)

    Returns:
        str: JSON response containing:
            - success (bool): Whether label was added
            - page_id (str): Page ID
            - labels (list): Updated list of all labels on the page
    """
    try:
        client = get_http_client()

        label_name = params.name.lower().replace(" ", "-")
        payload = [{"prefix": "global", "name": label_name}]

        response = await client.post(
            f"/rest/api/content/{params.page_id}/label",
            json=payload
        )
        response.raise_for_status()
        data = response.json()

        labels = [
            {"name": lbl.get("name"), "prefix": lbl.get("prefix"), "id": lbl.get("id")}
            for lbl in data.get("results", [])
        ]

        return json.dumps({
            "success": True,
            "page_id": params.page_id,
            "added_label": label_name,
            "labels": labels,
            "message": f"Label '{label_name}' added successfully"
        }, indent=2)

    except Exception as e:
        return json.dumps({"success": False, "error": _handle_api_error(e)}, indent=2)


@mcp.tool(
    name="confluence_search_user",
    annotations={
        "title": "Search Confluence Users",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def search_user(params: SearchUserInput) -> str:
    """Search for Confluence users by name or within a group.

    Searches users via CQL (type=user) or plain text. On Confluence DC,
    CQL user search is limited — use group_name to search group members instead.

    Args:
        params (SearchUserInput): Parameters containing:
            - query (str): Search query (plain text or CQL expression)
            - group_name (Optional[str]): Search within a specific group (DC fallback)
            - limit (int): Max results (default: 10)

    Returns:
        str: JSON response containing:
            - count (int): Number of users found
            - users (list): List of {username, display_name, email, user_key}
    """
    try:
        client = get_http_client()
        users = []

        if params.group_name:
            # DC: search group members
            response = await client.get(
                f"/rest/api/group/{params.group_name}/member",
                params={"limit": params.limit}
            )
            response.raise_for_status()
            data = response.json()
            raw_users = data.get("results", [])

            # Filter by query if provided
            q = params.query.lower()
            for u in raw_users:
                display = u.get("displayName", "")
                name = u.get("username", u.get("name", ""))
                if q in display.lower() or q in name.lower():
                    users.append({
                        "username": name,
                        "display_name": display,
                        "email": u.get("email", ""),
                        "user_key": u.get("userKey", u.get("accountId", ""))
                    })
        else:
            # CQL user search
            cql_keywords = ["type=", "user.fullname", "user.accountid", " AND ", " OR "]
            is_cql = any(kw in params.query for kw in cql_keywords)
            cql = params.query if is_cql else f'type=user AND user.fullname ~ "{params.query}"'

            response = await client.get(
                "/rest/api/search",
                params={"cql": cql, "limit": params.limit}
            )
            response.raise_for_status()
            data = response.json()

            for result in data.get("results", []):
                u = result.get("user", result)
                users.append({
                    "username": u.get("username", u.get("name", "")),
                    "display_name": u.get("displayName", ""),
                    "email": u.get("email", ""),
                    "user_key": u.get("userKey", u.get("accountId", ""))
                })

        return json.dumps({
            "success": True,
            "count": len(users),
            "users": users
        }, indent=2)

    except Exception as e:
        return json.dumps({"success": False, "error": _handle_api_error(e)}, indent=2)


if __name__ == "__main__":
    # Run the MCP server
    mcp.run()

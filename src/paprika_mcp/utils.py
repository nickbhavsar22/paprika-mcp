"""Utility functions for paprika-mcp server."""

import gzip
import json
import logging
import os
import re
import unicodedata
from datetime import date, timedelta
from typing import Any, cast

import requests
from paprika_recipes.cache import DirectoryCache
from paprika_recipes.remote import Remote

logger = logging.getLogger(__name__)

# Module-level cache for categories (persists for server lifetime)
_categories_cache: dict[str, dict[str, str]] | None = None

# Module-level cache for meal types (persists for server lifetime)
_meal_types_cache: list[dict[str, Any]] | None = None

# Paprika API base URL
PAPRIKA_API_BASE = "https://www.paprikaapp.com/api/v2/sync"


def get_credentials() -> tuple[str, str]:
    """Get Paprika credentials from environment variables or config file.

    Priority:
    1. PAPRIKA_EMAIL and PAPRIKA_PASSWORD environment variables
    2. ~/.paprika-mcp/config.json file

    Raises:
        ValueError: If credentials are not configured
    """
    # Check environment variables first
    email = os.environ.get("PAPRIKA_EMAIL")
    password = os.environ.get("PAPRIKA_PASSWORD")

    if email and password:
        return email, password

    # Check config file
    config_path = os.path.expanduser("~/.paprika-mcp/config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                config = json.load(f)
                email = config.get("email")
                password = config.get("password")
                if email and password:
                    return email, password
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to read config file: {e}")

    raise ValueError(
        "Paprika credentials not found. Set PAPRIKA_EMAIL and PAPRIKA_PASSWORD "
        "environment variables, or create ~/.paprika-mcp/config.json with "
        '{"email": "your@email.com", "password": "yourpassword"}'
    )


def get_user_agent() -> str | None:
    """Get User-Agent string from environment or config file.

    Priority:
    1. PAPRIKA_USER_AGENT environment variable
    2. user_agent field in ~/.paprika-mcp/config.json

    Note: If not configured here, the Remote class will auto-detect from
    the installed Paprika app.

    Returns:
        User-Agent string or None (which triggers auto-detection in Remote)
    """
    # Check environment variable first
    user_agent = os.environ.get("PAPRIKA_USER_AGENT")
    if user_agent:
        return user_agent

    # Check config file
    config_path = os.path.expanduser("~/.paprika-mcp/config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                config = json.load(f)
                user_agent = cast(str | None, config.get("user_agent"))
                if user_agent:
                    return user_agent
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to read user_agent from config file: {e}")

    return None


def get_remote() -> Remote:
    """Get authenticated Remote instance using stored credentials.

    The Remote class uses a DirectoryCache to store recipe data locally:
    - Recipe metadata (list of UIDs/hashes) is always fetched fresh from the API
    - Individual recipe details are cached in ~/.paprika-mcp/cache/
    - Cached recipes are keyed by UID and validated by hash
    - If a recipe's hash matches the cache, the cached version is used
    - If hash differs or not cached, recipe is fetched from API and cached

    Note: Remote.recipes is a generator that makes API calls. If you need to
    iterate multiple times or access by index, convert to list first.

    Raises:
        ValueError: If credentials are not configured
        PaprikaError: If authentication fails (check credentials)
        RequestError: If API request fails (network/server issue)
    """
    email, password = get_credentials()
    user_agent = get_user_agent()

    # Use cache to avoid re-downloading recipes
    cache_dir = os.path.expanduser("~/.paprika-mcp/cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache = DirectoryCache(cache_dir)

    try:
        # Use 30 second timeout to prevent hanging on network issues
        remote = Remote(email, password, cache=cache, user_agent=user_agent, timeout=30)
        # Test authentication by accessing bearer_token
        _ = remote.bearer_token
        return remote
    except Exception as e:
        logger.error(f"Failed to authenticate with Paprika API: {e}")
        logger.error(
            "Please verify your credentials in ~/.paprika-mcp/config.json "
            "or PAPRIKA_EMAIL/PAPRIKA_PASSWORD environment variables. "
            "You may also need to set a user_agent to mimic the official Paprika app."
        )
        raise


def get_categories(bearer_token: str) -> dict[str, Any]:
    """Get all categories from Paprika API with caching.

    Returns a dict with:
    - 'uid_to_name': mapping of UUID to category name
    - 'name_to_uid': mapping of lowercase name to UUID
    - 'all': list of all category dicts
    - 'by_uid': mapping of UUID to full category dict

    Results are cached for the lifetime of the server process.
    """
    global _categories_cache

    # Return cached version if available
    if _categories_cache is not None:
        return _categories_cache

    # Fetch from API
    headers = {"Authorization": f"Bearer {bearer_token}"}
    try:
        resp = requests.get(
            "https://www.paprikaapp.com/api/v2/sync/categories/",
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        categories = data.get("result", [])

        # Build mappings
        uid_to_name = {}
        name_to_uid = {}
        by_uid = {}

        for cat in categories:
            uid = cat["uid"]
            name = cat.get("name", "")
            if name:
                uid_to_name[uid] = name
                name_to_uid[name.lower()] = uid
                by_uid[uid] = cat

        _categories_cache = {
            "uid_to_name": uid_to_name,
            "name_to_uid": name_to_uid,
            "all": categories,
            "by_uid": by_uid,
        }

        return _categories_cache

    except requests.RequestException as e:
        logger.warning(f"Failed to fetch categories: {e}")
        # Return empty mappings on error
        return {
            "uid_to_name": {},
            "name_to_uid": {},
            "all": [],
            "by_uid": {},
        }


def translate_category_uids(uids: list[str], bearer_token: str) -> str:
    """Translate a list of category UUIDs to comma-separated names.

    Args:
        uids: List of category UUIDs
        bearer_token: Paprika API bearer token

    Returns:
        Comma-separated string of category names
    """
    if not uids:
        return ""

    categories = get_categories(bearer_token)
    uid_to_name = categories["uid_to_name"]

    names = [uid_to_name.get(uid, f"Unknown-{uid[:8]}") for uid in uids]
    return ", ".join(names)


def normalize_string(text: str) -> str:
    """Normalize unicode string for comparison.

    Uses NFD normalization to decompose accented characters,
    making comparisons work across different unicode representations.
    """
    return unicodedata.normalize("NFD", text).lower()


def search_in_text(
    text: str, query: str, context_lines: int = 2, regex: bool = False
) -> list[dict[str, Any]]:
    """Search for query in text and return matches with context.

    Args:
        text: Text to search in
        query: Search query (plain text or regex pattern)
        context_lines: Number of lines of context around matches
        regex: If True, treat query as a regex pattern

    Returns list of dicts with 'line', 'match', and 'context' keys.
    """
    if not text:
        return []

    matches = []
    lines = text.split("\n")

    if regex:
        import re

        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error as e:
            # Invalid regex - return empty results
            logger.warning(f"Invalid regex pattern '{query}': {e}")
            return []

        for i, line in enumerate(lines):
            if pattern.search(line):
                # Get context lines before and after
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)
                context = "\n".join(lines[start:end])

                matches.append(
                    {"line": i + 1, "match": line.strip(), "context": context}
                )
    else:
        query_lower = query.lower()
        for i, line in enumerate(lines):
            if query_lower in line.lower():
                # Get context lines before and after
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)
                context = "\n".join(lines[start:end])

                matches.append(
                    {"line": i + 1, "match": line.strip(), "context": context}
                )

    return matches


# --- Meal utilities ---


def get_meal_types(bearer_token: str) -> list[dict[str, Any]]:
    """Get meal types from Paprika API with caching.

    Returns a list of meal type dicts with keys:
    uid, name, order_flag, color, export_all_day, export_time, original_type.

    Results are cached for the lifetime of the server process.
    """
    global _meal_types_cache

    if _meal_types_cache is not None:
        return _meal_types_cache

    headers = {"Authorization": f"Bearer {bearer_token}"}
    try:
        resp = requests.get(
            f"{PAPRIKA_API_BASE}/mealtypes/",
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        _meal_types_cache = resp.json().get("result", [])
        return _meal_types_cache
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch meal types: {e}")
        return []


def meal_type_int_to_name(type_int: int, bearer_token: str) -> str:
    """Convert a meal type integer to its display name.

    Falls back to 'Type {n}' if the type is not found.
    """
    meal_types = get_meal_types(bearer_token)
    for mt in meal_types:
        if mt.get("original_type") == type_int:
            return mt["name"]
    return f"Type {type_int}"


def meal_type_name_to_int(name: str, bearer_token: str) -> int | None:
    """Convert a meal type name to its integer value.

    Returns None if the name is not recognized.
    """
    meal_types = get_meal_types(bearer_token)
    name_lower = name.lower()
    for mt in meal_types:
        if mt.get("name", "").lower() == name_lower:
            return mt["original_type"]
    return None


def meal_type_to_uid(type_int: int, bearer_token: str) -> str:
    """Get the type_uid for a meal type integer."""
    meal_types = get_meal_types(bearer_token)
    for mt in meal_types:
        if mt.get("original_type") == type_int:
            return mt["uid"]
    return ""


def get_meals(bearer_token: str) -> list[dict[str, Any]]:
    """Fetch all non-deleted meals from Paprika API.

    Returns a list of meal dicts sorted by date, then type, then order_flag.
    """
    headers = {"Authorization": f"Bearer {bearer_token}"}
    try:
        resp = requests.get(
            f"{PAPRIKA_API_BASE}/meals/",
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        meals = resp.json().get("result", [])
        # Sort by date, then type, then order_flag
        meals.sort(
            key=lambda m: (
                m.get("date", ""),
                m.get("type", 0),
                m.get("order_flag", 0),
            )
        )
        return meals
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch meals: {e}")
        return []


def save_meal(bearer_token: str, meal_data: dict[str, Any]) -> dict[str, Any]:
    """Create or update a meal via the Paprika API.

    The API expects a gzip-compressed JSON list posted as multipart form-data.

    Returns dict with 'success' bool and optional 'error' message.
    """
    headers = {"Authorization": f"Bearer {bearer_token}"}
    try:
        compressed = gzip.compress(json.dumps([meal_data]).encode("utf-8"))
        resp = requests.post(
            f"{PAPRIKA_API_BASE}/meals/",
            headers=headers,
            files={"data": compressed},
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        if "error" in result:
            return {"success": False, "error": result["error"].get("message", "Unknown error")}
        return {"success": True}
    except requests.RequestException as e:
        return {"success": False, "error": str(e)}


def resolve_date(date_str: str) -> str:
    """Resolve a flexible date string to YYYY-MM-DD format.

    Supports:
        - YYYY-MM-DD (passthrough)
        - 'today', 'tomorrow', 'yesterday'
        - Day names: 'monday' through 'sunday' (next occurrence including today)
        - 'next monday' through 'next sunday' (always at least 1 day ahead)

    Raises:
        ValueError: If the date string cannot be parsed.
    """
    s = date_str.strip().lower()

    # Check YYYY-MM-DD format
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s

    today = date.today()

    if s == "today":
        return today.isoformat()
    if s == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    if s == "yesterday":
        return (today - timedelta(days=1)).isoformat()

    day_names = [
        "monday", "tuesday", "wednesday", "thursday",
        "friday", "saturday", "sunday",
    ]

    # "next monday" etc. - always at least 1 day in the future
    next_match = re.match(r"^next\s+(\w+)$", s)
    if next_match:
        day_name = next_match.group(1)
        if day_name in day_names:
            target = day_names.index(day_name)
            current = today.weekday()
            days_ahead = (target - current) % 7
            if days_ahead == 0:
                days_ahead = 7
            return (today + timedelta(days=days_ahead)).isoformat()

    # Plain day name - next occurrence including today
    if s in day_names:
        target = day_names.index(s)
        current = today.weekday()
        days_ahead = (target - current) % 7
        return (today + timedelta(days=days_ahead)).isoformat()

    raise ValueError(
        f"Cannot parse date '{date_str}'. "
        "Use YYYY-MM-DD, 'today', 'tomorrow', 'yesterday', "
        "a day name like 'monday', or 'next monday'."
    )


# --- Grocery utilities ---

# Module-level caches (persist for server lifetime)
_grocery_lists_cache: list[dict[str, Any]] | None = None
_grocery_aisles_cache: list[dict[str, Any]] | None = None


def get_grocery_lists(bearer_token: str) -> list[dict[str, Any]]:
    """Get all grocery lists from Paprika API with caching.

    Returns list of dicts with keys: uid, name, order_flag, is_default, reminders_list.
    Sorted by order_flag.
    """
    global _grocery_lists_cache

    if _grocery_lists_cache is not None:
        return _grocery_lists_cache

    headers = {"Authorization": f"Bearer {bearer_token}"}
    try:
        resp = requests.get(
            f"{PAPRIKA_API_BASE}/grocerylists/",
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        _grocery_lists_cache = resp.json().get("result", [])
        _grocery_lists_cache.sort(key=lambda gl: gl.get("order_flag", 0))
        return _grocery_lists_cache
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch grocery lists: {e}")
        return []


def get_grocery_aisles(bearer_token: str) -> list[dict[str, Any]]:
    """Get all grocery aisles from Paprika API with caching.

    Returns list of dicts with keys: uid, name, order_flag.
    Sorted by order_flag.
    """
    global _grocery_aisles_cache

    if _grocery_aisles_cache is not None:
        return _grocery_aisles_cache

    headers = {"Authorization": f"Bearer {bearer_token}"}
    try:
        resp = requests.get(
            f"{PAPRIKA_API_BASE}/groceryaisles/",
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        _grocery_aisles_cache = resp.json().get("result", [])
        _grocery_aisles_cache.sort(key=lambda a: a.get("order_flag", 0))
        return _grocery_aisles_cache
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch grocery aisles: {e}")
        return []


def resolve_grocery_list(
    name_or_uid: str | None, bearer_token: str
) -> dict[str, Any] | None:
    """Resolve a grocery list by name (case-insensitive) or UID.

    If name_or_uid is None, returns the default list.
    Returns the list dict, or None if not found.
    """
    lists = get_grocery_lists(bearer_token)
    if not lists:
        return None

    if name_or_uid is None:
        # Return the default list
        for gl in lists:
            if gl.get("is_default"):
                return gl
        return lists[0] if lists else None

    # Try UID match first
    for gl in lists:
        if gl["uid"] == name_or_uid:
            return gl

    # Try name match (case-insensitive)
    name_lower = name_or_uid.lower()
    for gl in lists:
        if gl.get("name", "").lower() == name_lower:
            return gl

    return None


def resolve_aisle_uid(aisle_name: str, bearer_token: str) -> str:
    """Resolve an aisle name to its UID. Returns empty string if not found."""
    aisles = get_grocery_aisles(bearer_token)
    name_lower = aisle_name.lower()
    for a in aisles:
        if a.get("name", "").lower() == name_lower:
            return a["uid"]
    return ""


def get_groceries(bearer_token: str) -> list[dict[str, Any]]:
    """Fetch all grocery items from Paprika API.

    Returns a list of grocery dicts sorted by aisle then order_flag.
    """
    headers = {"Authorization": f"Bearer {bearer_token}"}
    try:
        resp = requests.get(
            f"{PAPRIKA_API_BASE}/groceries/",
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        items = resp.json().get("result", [])
        items.sort(
            key=lambda i: (
                i.get("aisle", ""),
                i.get("order_flag", 0),
            )
        )
        return items
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch groceries: {e}")
        return []


def save_grocery(
    bearer_token: str, item_data: dict[str, Any]
) -> dict[str, Any]:
    """Create or update a grocery item via the Paprika API.

    The API expects a gzip-compressed JSON list posted as multipart form-data.

    Returns dict with 'success' bool and optional 'error' message.
    """
    headers = {"Authorization": f"Bearer {bearer_token}"}
    try:
        compressed = gzip.compress(json.dumps([item_data]).encode("utf-8"))
        resp = requests.post(
            f"{PAPRIKA_API_BASE}/groceries/",
            headers=headers,
            files={"data": compressed},
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        if "error" in result:
            return {
                "success": False,
                "error": result["error"].get("message", "Unknown error"),
            }
        return {"success": True}
    except requests.RequestException as e:
        return {"success": False, "error": str(e)}

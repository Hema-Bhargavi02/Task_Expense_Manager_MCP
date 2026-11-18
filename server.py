
import os

import httpx
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("Expense Manager")

API_URL = os.getenv(
    "API_URL",
    "http://localhost:8080"
)

ACCESS_TOKEN = os.getenv("EXPENSE_ACCESS_TOKEN")


def get_headers():

    if not ACCESS_TOKEN:
        raise ValueError(
            "JWT access token is missing."
        )

    return {
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }


def backend_error(response):
    """Build a readable error from the backend's ApiError JSON body."""
    status = response.status_code
    message = None

    try:
        body = response.json()

        if isinstance(body, dict):
            message = (
                body.get("message")
                or body.get("detail")
                or body.get("error")
            )
    except ValueError:
        message = None

    if not message:
        message = f"Backend returned HTTP {status}."

    return {
        "error": message,
        "status": status
    }


@mcp.tool()
async def add_expense(
    amount: float,
    category: str,
    description: str = "",
    expense_date: str = ""
) -> dict:
    """Add an expense for the authenticated user.

    expense_date should use YYYY-MM-DD format.
    Leave it empty to use today's date.
    """

    if amount <= 0:
        return {
            "error": "Amount must be greater than zero."
        }

    if not category.strip():
        return {
            "error": "Category cannot be empty."
        }

    payload = {
        "amount": amount,
        "category": category,
        "description": description,
        "expenseDate": expense_date or None
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:

            response = await client.post(
                f"{API_URL}/expense/add",
                json=payload,
                headers=get_headers()
            )

            response.raise_for_status()

            return response.json()

    except httpx.HTTPStatusError as error:
        return backend_error(error.response)

    except httpx.RequestError as error:
        return {
            "error": f"Cannot connect to Spring Boot: {error}"
        }

    except ValueError as error:
        return {"error": str(error)}


@mcp.tool()
async def get_expenses_by_period(
    start_date: str,
    end_date: str,
    page: int = 0,
    size: int = 10
) -> dict:
    """Get one page of the authenticated user's expenses.

    Returns the expenses between two dates (inclusive), ordered
    newest-added first (by created_at, descending).

    Dates must use YYYY-MM-DD format.

    Paging: page 0 is the first `size` rows, page 1 the next
    `size` rows, and so on. The response contains:
    items, page, size, totalItems, totalPages, hasNext,
    totalAmount (the amount sum for the whole period).
    Use hasNext to decide whether another page exists.
    """

    try:
        async with httpx.AsyncClient(timeout=15) as client:

            response = await client.get(
                f"{API_URL}/expense/period",
                params={
                    "startDate": start_date,
                    "endDate": end_date,
                    "page": page,
                    "size": size
                },
                headers=get_headers()
            )

            response.raise_for_status()

            return response.json()

    except httpx.HTTPStatusError as error:
        return backend_error(error.response)

    except httpx.RequestError as error:
        return {
            "error": f"Cannot connect to Spring Boot: {error}"
        }

    except ValueError as error:
        return {"error": str(error)}


@mcp.tool()
async def find_expenses_for_deletion(
    category: str = "",
    start_date: str = "",
    end_date: str = ""
) -> dict:
    """Find the expenses that match a delete request.

    Always call this before deleting anything.

    - category: restrict the search to one category
      (case-insensitive). Leave it empty when the user did not
      mention a category.
    - start_date / end_date: optional YYYY-MM-DD bounds. Leave them
      empty to search the user's whole history.

    Returns items (each with id, expenseDate, amount, category and
    description), count, and requires_confirmation. When
    requires_confirmation is true you must list the items and ask
    the user whether to delete all of them or only specific ids
    before deleting anything.
    """

    params = {}

    if category.strip():
        params["category"] = category.strip()

    if start_date:
        params["startDate"] = start_date

    if end_date:
        params["endDate"] = end_date

    try:
        async with httpx.AsyncClient(timeout=15) as client:

            response = await client.get(
                f"{API_URL}/expense/search",
                params=params,
                headers=get_headers()
            )

            response.raise_for_status()

            items = response.json()

            if not isinstance(items, list):
                return {
                    "error": (
                        "The backend returned an unexpected "
                        "search result."
                    )
                }

            return {
                "items": items,
                "count": len(items),
                "requires_confirmation": (
                    bool(items)
                    and (
                        bool(category.strip())
                        or len(items) > 1
                    )
                )
            }

    except httpx.HTTPStatusError as error:
        return backend_error(error.response)

    except httpx.RequestError as error:
        return {
            "error": f"Cannot connect to Spring Boot: {error}"
        }

    except ValueError as error:
        return {"error": str(error)}


@mcp.tool()
async def delete_expenses(
    expense_ids: list[int]
) -> dict:
    """Delete several expenses after the user confirmed them.

    Pass the exact ids returned by find_expenses_for_deletion.
    Use this for both "delete all" and a user-selected subset.
    """

    unique_ids = list(dict.fromkeys(expense_ids))

    if not unique_ids:
        return {"error": "No expense ids were provided."}

    deleted = []
    failed = []

    async with httpx.AsyncClient(timeout=15) as client:

        for expense_id in unique_ids:

            try:
                response = await client.delete(
                    f"{API_URL}/expense/delete/{expense_id}",
                    headers=get_headers()
                )

                response.raise_for_status()
                deleted.append(expense_id)

            except httpx.HTTPStatusError as error:
                failed.append({
                    "id": expense_id,
                    **backend_error(error.response)
                })

            except httpx.RequestError as error:
                failed.append({
                    "id": expense_id,
                    "error": (
                        "Cannot connect to Spring Boot: "
                        f"{error}"
                    )
                })

            except ValueError as error:
                failed.append({
                    "id": expense_id,
                    "error": str(error)
                })

    return {
        "deleted": deleted,
        "failed": failed
    }


@mcp.tool()
async def delete_expense(
    expense_id: int
) -> dict:
    """Delete an expense belonging to the authenticated user."""

    try:
        async with httpx.AsyncClient(timeout=15) as client:

            response = await client.delete(
                f"{API_URL}/expense/delete/{expense_id}",
                headers=get_headers()
            )

            response.raise_for_status()

            return {
                "success": True,
                "message": f"Expense {expense_id} deleted."
            }

    except httpx.HTTPStatusError as error:
        return backend_error(error.response)

    except httpx.RequestError as error:
        return {
            "error": f"Cannot connect to Spring Boot: {error}"
        }

    except ValueError as error:
        return {"error": str(error)}


if __name__ == "__main__":
    mcp.run(transport="stdio")

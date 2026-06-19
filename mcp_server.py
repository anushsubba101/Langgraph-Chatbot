# server.py
from fastmcp import FastMCP
import sqlite3
import os

mcp = FastMCP("expense-tracker")

def get_db():
    conn = sqlite3.connect("expenses.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, category TEXT,
            amount REAL, description TEXT
        )
    """)
    conn.commit()
    return conn

@mcp.tool()
def add_expense(date: str, category: str, amount: float, description: str) -> str:
    """Add a new expense entry to the database."""
    conn = get_db()
    conn.execute("INSERT INTO expenses VALUES (NULL,?,?,?,?)", (date, category, amount, description))
    conn.commit()
    return f"Added: {category} - ${amount}"

@mcp.tool()
def list_expenses(start_date: str, end_date: str) -> list:
    """List expense entries within an inclusive date range."""
    rows = get_db().execute(
        "SELECT date, category, amount, description FROM expenses WHERE date BETWEEN ? AND ?",
        (start_date, end_date)
    ).fetchall()
    return [{"date": r[0], "category": r[1], "amount": r[2], "description": r[3]} for r in rows]

@mcp.tool()
def summarize(start_date: str, end_date: str) -> dict:
    """Summarize expenses by category within an inclusive date range."""
    rows = get_db().execute(
        "SELECT category, SUM(amount) FROM expenses WHERE date BETWEEN ? AND ? GROUP BY category",
        (start_date, end_date)
    ).fetchall()
    return {r[0]: r[1] for r in rows}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
from __future__ import annotations
from fastmcp import FastMCP

mcp = FastMCP("arith")

def _as_number(x):
    # Accept ints/floats or numeric strings; raise clean errors otherwise
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x,str):
        return float(x.strip())
    raise TypeError("Expected a number (int/float or numeric string)")

@mcp.tool()
async def add(a: float, b: float) -> float:
    """Return a + b."""
    return _as_number(a) + _as_number(b)

@mcp.tool()
async def subtract(a: float, b: float) -> float:
    """Return a-b."""
    return _as_number(a) - _as_number(b)

@mcp.tool()
async def multiply(a: float, b:float) -> float:
    """Return a*b."""
    return _as_number(a) * _as_number(b)

@mcp.tool()
async def divide(a: float, b:float) -> float:
    """Return a/b."""
    a = _as_number(a)
    b = _as_number(b)
    if b == 0:
        raise ZeroDivisionError("Division by zero")
    return a/b

@mcp.tool()
async def power(a: float, b:float) -> float:
    """Return a**b."""
    return _as_number(a) ** _as_number(b)

@mcp.tool()
async def modulus(a:float, b:float) -> float:
    """Return a % b. Rasie on modulus by zero."""
    a = _as_number(a)
    b = _as_number(b)
    if b == 0:
        raise ZeroDivisionError("Modulus by Zero")
    return a % b

@mcp.resource("data://config")
def get_config() -> dict:
    return {"theme": "dark", "version": "1.0"}

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=9000)
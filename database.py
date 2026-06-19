from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import tool, BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from dotenv import load_dotenv
import sqlite3
import requests
import aiosqlite
import asyncio
import threading

load_dotenv()

# Dedicated async loop for backend tasks
_ASYNC_LOOP = asyncio.new_event_loop()
_ASYNC_THREAD = threading.Thread(target=_ASYNC_LOOP.run_forever, daemon=True)
_ASYNC_THREAD.start()


def _submit_async(coro):
    return asyncio.run_coroutine_threadsafe(coro, _ASYNC_LOOP)


def run_async(coro):
    return _submit_async(coro).result()


def submit_async_task(coro):
    """Schedule a coroutine on the backend event loop."""
    return _submit_async(coro)

model = ChatGroq(model="llama-3.3-70b-versatile")
# search tools
search_tool = DuckDuckGoSearchRun(region="us-en")

# tools

@tool
def get_stock_price(symbol: str) -> dict:
    """Fetch the latest stock price for a given ticker symbol (e.g. 'AAPL', 'TSLA')."""
    url = (
        f"https://www.alphavantage.co/query"
        f"?function=GLOBAL_QUOTE"   # ✅ available on free tier
        f"&symbol={symbol}"
        f"&apikey=G53I02D463KO9F0W"
    )
    r = requests.get(url)
    data = r.json()

    # ✅ Return a clean dict instead of raw API response
    quote = data.get("Global Quote", {})
    if not quote:
        return {"error": "Symbol not found or API limit reached"}

    return {
        "symbol": quote.get("01. symbol"),
        "price": quote.get("05. price"),
        "change": quote.get("09. change"),
        "change_percent": quote.get("10. change percent"),
        "volume": quote.get("06. volume"),
        "latest_trading_day": quote.get("07. latest trading day"),
    }

client = MultiServerMCPClient(
    {
        "arith": {
            "transport": "stdio",
            "command": "python3",
            "args": ["D:\langgraph-chatbot\main.py"],
        },
        "expense": {
            "transport": "streamable_http",
            "url": "https://complete-blue-bobolink.fastmcp.app/mcp",
            "headers": {
                "Authorization": "Bearer YOUR_TOKEN_HERE"
            }
        }
    }
)

def load_mcp_tools() -> list[BaseTool]:
    try:
        return run_async(client.get_tools())
    except Exception:
        return []

mcp_tools = load_mcp_tools()
tools = [search_tool, get_stock_price, *mcp_tools]
llm_with_tools = model.bind_tools(tools) if tools else model

#---------state--------------------------------------------------------------------------------------------
class ChatState(TypedDict):
# state doesnot handle chat histry i.e message gets updated every time new messages is added so we use reducer function inorder to maintian chain history. here instead of operator.add function i have used add_messages
    messages: Annotated[list[BaseMessage], add_messages]

#-----------nodes--------------------------------------------------------------------------------------------
async def chat_node(state: ChatState):
    # take user query from state
    messages = state['messages']
    # send to llm
    response = await llm_with_tools.ainvoke(messages)
    # response store state
    return {'messages': [response]}

tool_node = ToolNode(tools) if tools else None

#----------------checkpointer--------------------------------------------------------------------
async def _init_checkpointer():
    conn = await aiosqlite.connect(database="chatbot.db")
    return AsyncSqliteSaver(conn)


checkpointer = run_async(_init_checkpointer())


#-----------------graph--------------------------------------------------------------------
graph = StateGraph(ChatState)

# add nodes
graph.add_node("chat_node", chat_node)
graph.add_edge(START, "chat_node")

if tool_node:
    graph.add_node("tools", tool_node)
    graph.add_conditional_edges("chat_node", tools_condition)
    graph.add_edge("tools", "chat_node")
else:
    graph.add_edge("chat_node", END)

workflow = graph.compile(checkpointer=checkpointer)

def retrieve_all_threads():
    all_threads = []
    seen = set()
    
    # list() returns checkpoints newest-first, so first occurrence = latest thread
    for checkpoint in checkpointer.list(None):
        thread_id = checkpoint.config['configurable']['thread_id']
        if thread_id not in seen:
            seen.add(thread_id)
            all_threads.append(thread_id)
    
    # Reverse so index [-1] = most recent
    return list(reversed(all_threads))
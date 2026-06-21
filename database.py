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
from langchain_core.messages import ToolMessage
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
search_tool = DuckDuckGoSearchRun(region="us-en")

@tool
def get_stock_price(symbol: str) -> dict:
    """Fetch the latest stock price for a given ticker symbol (e.g. 'AAPL', 'TSLA')."""
    url = (
        f"https://www.alphavantage.co/query"
        f"?function=GLOBAL_QUOTE"
        f"&symbol={symbol}"
        f"&apikey=G53I02D463KO9F0W"
    )
    r = requests.get(url)
    data = r.json()

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
        "expense": {
            "transport": "streamable_http",
            "url": "https://langgraph-chatbot-production-9f18.up.railway.app/mcp"
        }
    }
)

# def load_mcp_tools() -> list[BaseTool]:
#     try:
#         return run_async(client.get_tools())
#     except Exception:
#         return []

def load_mcp_tools() -> list[BaseTool]:
    try:
        tools = run_async(client.get_tools())
        print("✅ Loaded MCP tools:", [t.name for t in tools])
        return tools
    except Exception as e:
        print(f"❌ MCP tools load error: {type(e).__name__}: {e}")
        if hasattr(e, 'exceptions'):
            for sub in e.exceptions:
                print(f"   ↳ Sub-exception: {type(sub).__name__}: {sub}")
        return []

mcp_tools = load_mcp_tools()
tools = [search_tool, get_stock_price, *mcp_tools]
llm_with_tools = model.bind_tools(tools) if tools else model

#---------state--------------------------------------------------------------------------------------------
class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

#-----------nodes--------------------------------------------------------------------------------------------
async def chat_node(state: ChatState):
    messages = state['messages']
    
    # Filter out empty tool messages
    cleaned = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            if msg.content and msg.content != [] and msg.content != "":
                cleaned.append(msg)
            else:
                cleaned.append(ToolMessage(
                    content="No result returned.",
                    tool_call_id=msg.tool_call_id
                ))
        else:
            cleaned.append(msg)
    
    response = await llm_with_tools.ainvoke(cleaned)
    return {'messages': [response]}

tool_node = ToolNode(tools) if tools else None

#----------------checkpointer--------------------------------------------------------------------
async def _init_checkpointer():
    conn = await aiosqlite.connect(database="chatbot.db")
    return AsyncSqliteSaver(conn)


checkpointer = run_async(_init_checkpointer())


#-----------------graph--------------------------------------------------------------------
graph = StateGraph(ChatState)

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
    
    for checkpoint in checkpointer.list(None):
        thread_id = checkpoint.config['configurable']['thread_id']
        if thread_id not in seen:
            seen.add(thread_id)
            all_threads.append(thread_id)
    
    return list(reversed(all_threads))
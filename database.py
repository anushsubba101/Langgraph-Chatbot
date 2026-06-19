from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import tool
from dotenv import load_dotenv
import sqlite3
import requests

load_dotenv()

# search tools

search_tool = DuckDuckGoSearchRun(region="us-en")

# tools
@tool
def calculator(first_num: float, second_num: float, operation:str) -> dict:
    """
    Perform a basic arithmetic operation on two numbers.
    supported operations: add, sub, mul, div
    """

    try:
        if operation == "add":
            result = first_num + second_num
        elif operation == "sub":
            result = first_num - second_num
        elif operation == "mul":
            result = first_num * second_num
        elif operation == "div":
            if second_num == 0:
                return{"error": "Division by zero is not allowed"}
            result = first_num / second_num
        else:
            return {"error": f"unsupported operation '{operation}' "}
        
        return{"first_num": first_num, "second_num": second_num, "operation": operation , "result" : result}
    except Exception as e:
        return{"error": str (e)}   

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

tools = [search_tool, calculator, get_stock_price]
    

model = ChatGroq(model="llama-3.3-70b-versatile").bind_tools(tools)

class ChatState(TypedDict):
# state doesnot handle chat histry i.e message gets updated every time new messages is added so we use reducer function inorder to maintian chain history. here instead of operator.add function i have used add_messages
    messages: Annotated[list[BaseMessage], add_messages]


def chat_node(state: ChatState):

    # take user query from state
    messages = state['messages']
    # send to llm
    response = model.invoke(messages)
    # response store state
    return {'messages': [response]}

tool_node = ToolNode(tools)

#databse creation
conn = sqlite3.connect(database='chatbot.db', check_same_thread=False)

# checkpointer
checkpointer = SqliteSaver(conn=conn)

graph = StateGraph(ChatState)

# add nodes
graph.add_node('chat_node',chat_node)
graph.add_node("tools", tool_node)

# add edges
graph.add_edge(START,'chat_node')
graph.add_conditional_edges("chat_node",tools_condition)
graph.add_edge('tools','chat_node')

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
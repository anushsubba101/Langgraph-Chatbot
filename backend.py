from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.message import add_messages
from dotenv import load_dotenv

load_dotenv()

model = ChatGroq(model="llama-3.3-70b-versatile")

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


checkpointer = InMemorySaver()

graph = StateGraph(ChatState)

# add nodes
graph.add_node('chat_node',chat_node)

# add edges

graph.add_edge(START,'chat_node')
graph.add_edge('chat_node',END)

workflow = graph.compile(checkpointer=checkpointer)

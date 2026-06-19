import streamlit as st
from database import workflow, retrieve_all_threads
from langchain_core.messages import HumanMessage
import uuid


# ── Utility functions ──────────────────────────────────────────────────────────

def generate_thread_id() -> str:
    return str(uuid.uuid4())

def reset_chat():
    thread_id = generate_thread_id()
    st.session_state["thread_id"] = thread_id
    st.session_state["message_history"] = []

    # ✅ Only append if not already in list
    if thread_id not in st.session_state["chat_threads"]:
        st.session_state["chat_threads"].append(thread_id)

def load_conversation(thread_id: str) -> list[dict]:
    """Return message_history-style dicts for a given thread, or [] on failure."""
    try:
        state = workflow.get_state(
            config={"configurable": {"thread_id": thread_id}}
        )
        raw_messages = state.values.get("messages", [])
    except Exception:
        return []

    result = []
    for msg in raw_messages:
        role = "user" if isinstance(msg, HumanMessage) else "assistant"
        # content can be a string or a list of content blocks
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        result.append({"role": role, "content": content})
    return result

def safe_chunk_content(chunk_content) -> str:
    """Coerce a message chunk's content to a plain string."""
    if isinstance(chunk_content, str):
        return chunk_content
    if isinstance(chunk_content, list):
        # content blocks: extract text parts only
        return "".join(
            block.get("text", "") for block in chunk_content if isinstance(block, dict)
        )
    return ""

def ai_chunks(user_input, config):
    """Yield only clean text chunks from the chat_node."""
    for chunk, metadata in workflow.stream(
        {"messages": [HumanMessage(content=user_input)]},
        config=config,
        stream_mode="messages",
    ):
        if (
            metadata.get("langgraph_node") == "chat_node"
            and not getattr(chunk, "tool_calls", None)
        ):
            text = safe_chunk_content(chunk.content)
            if text:
                yield text


# ── Session state bootstrap ────────────────────────────────────────────────────

if "chat_threads" not in st.session_state:
    existing_threads = retrieve_all_threads()
    st.session_state["chat_threads"] = existing_threads

if "thread_id" not in st.session_state:
    existing_threads = st.session_state["chat_threads"]

    if existing_threads:
        # ✅ Load the most recent thread instead of creating a new one
        latest_thread = existing_threads[-1]
        st.session_state["thread_id"] = latest_thread
        st.session_state["message_history"] = load_conversation(latest_thread)
    else:
        # ✅ Only create new thread if no threads exist at all
        thread_id = generate_thread_id()
        st.session_state["thread_id"] = thread_id
        st.session_state["chat_threads"].append(thread_id)
        st.session_state["message_history"] = []

if "message_history" not in st.session_state:
    st.session_state["message_history"] = []


# ── Sidebar ────────────────────────────────────────────────────────────────────

st.sidebar.title("LangGraph Chatbot")

if st.sidebar.button("➕ New Chat"):
    reset_chat()
    st.rerun()

st.sidebar.header("My Conversations")

for i, thread_id in enumerate(reversed(st.session_state["chat_threads"])):
    label = f"Chat {len(st.session_state['chat_threads']) - i}  · {str(thread_id)[:8]}…"
    is_active = thread_id == st.session_state["thread_id"]

    if st.sidebar.button(label, key=f"thread_{thread_id}", disabled=is_active):
        st.session_state["thread_id"] = thread_id
        st.session_state["message_history"] = load_conversation(thread_id)
        st.rerun()


# ── Main chat UI ───────────────────────────────────────────────────────────────

for message in st.session_state["message_history"]:
    with st.chat_message(message["role"]):
        st.write(message["content"])          # write handles markdown; use st.text if you prefer plain

user_input = st.chat_input("Type here…")

if user_input:
    st.session_state["message_history"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    # config = {"configurable": {"thread_id": st.session_state["thread_id"]}}

    config = {
        "configurable": {"thread_id": st.session_state["thread_id"]},
        "metadata": {
            "thread_id": st.session_state["thread_id"]
        },
        "run_name": "chat_turn",
    }

    with st.chat_message("assistant"):
        ai_message = st.write_stream(
            ai_chunks(user_input, config)
    )

    st.session_state["message_history"].append(
        {"role": "assistant", "content": ai_message}
    )
import streamlit as st
from backend import workflow
from langchain_core.messages import HumanMessage
import uuid


# ── Utility functions ──────────────────────────────────────────────────────────

def generate_thread_id() -> str:
    return str(uuid.uuid4())

def reset_chat():
    thread_id = generate_thread_id()
    st.session_state["thread_id"] = thread_id
    st.session_state["chat_threads"].append(thread_id)
    st.session_state["message_history"] = []

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


# ── Session state bootstrap ────────────────────────────────────────────────────

if "chat_threads" not in st.session_state:
    st.session_state["chat_threads"] = []

if "thread_id" not in st.session_state:
    thread_id = generate_thread_id()
    st.session_state["thread_id"] = thread_id
    st.session_state["chat_threads"].append(thread_id)

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

    config = {"configurable": {"thread_id": st.session_state["thread_id"]}}

    with st.chat_message("assistant"):
        ai_message = st.write_stream(
            safe_chunk_content(chunk.content)
            for chunk, _metadata in workflow.stream(
                {"messages": [HumanMessage(content=user_input)]},
                config=config,
                stream_mode="messages",
            )
            if safe_chunk_content(chunk.content)   # skip empty chunks
        )

    st.session_state["message_history"].append(
        {"role": "assistant", "content": ai_message}
    )
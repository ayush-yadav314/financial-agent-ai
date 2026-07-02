import streamlit as st
from langchain_core.messages import HumanMessage
from agent import financial_agent_app

# Set up the browser page title and layout
st.set_page_config(page_title="Agentic Finance Analyst", page_icon="📈", layout="centered")
st.title("🤖 Multi-Agent Financial Research System")
st.caption("Driven by LangGraph State Workflows & Gemini AI")

# Maintain historical context across computational updates (Session State)
if "messages" not in st.session_state:
    st.session_state.messages = []

# Render chronological chat logs on the screen
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Create the user text input bar at the bottom
user_input = st.chat_input("Ask about a stock (e.g., 'Is Nvidia a good buy right now?')")

if user_input:
    # 1. Display the user's question instantly in the UI
    st.chat_message("user").markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})
    
    # 2. Pack parameters inside the LangGraph state dictionary
    inputs = {"messages": [HumanMessage(content=user_input)]}
    
    # 3. Stream the graph execution with a visual loading spinner
    with st.spinner("Agents are parsing ticker, gathering metrics, and checking news loops..."):
        try:
            # Execute our compiled LangGraph workflow machine
            output = financial_agent_app.invoke(inputs)
            # Pull the absolute last message returned from the finalized graph state (the Analyst Node output)
            final_reply = output["messages"][-1].content
        except Exception as e:
            final_reply = f"⚠️ An error occurred during agent execution: {str(e)}\n\n*Make sure your API keys in the `.env` file are correct.*"

    # 4. Render the agent's finalized structural report response
    with st.chat_message("assistant"):
        st.markdown(final_reply)
    st.session_state.messages.append({"role": "assistant", "content": final_reply})
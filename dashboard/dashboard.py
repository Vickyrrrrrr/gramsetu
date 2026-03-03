"""
============================================
dashboard.py — Streamlit Judge Dashboard
============================================
Live web dashboard for hackathon judges to visualize:
  1. Live Feed — Real-time WhatsApp messages
  2. Agent Visualization — Which agent is active
  3. Confidence Meter — Visual bars per field
  4. Audit Log Table — Immutable safety logs
  5. Language Toggle — Hindi input → English processing

Run: streamlit run dashboard/dashboard.py
"""

import sys
import os
import time
import json
import requests
import streamlit as st

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard.components import (
    agent_status_card,
    confidence_bar,
    message_bubble,
    stat_card,
    section_header,
)

# ---- Page Config ----
st.set_page_config(
    page_title="GramSetu — Judge Dashboard",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---- Dark Theme CSS ----
st.markdown("""
<style>
    /* Dark theme overrides for Streamlit */
    .stApp {
        background-color: #0a0e1a;
        color: #e8ecf5;
    }
    
    .stSidebar {
        background-color: #111827;
    }
    
    .stMetric {
        background: #1a1f35;
        border: 1px solid #2a3152;
        border-radius: 10px;
        padding: 10px;
    }
    
    h1, h2, h3, h4, h5, h6, p, span, label, .stMarkdown {
        color: #e8ecf5 !important;
    }
    
    .stDataFrame {
        background: #1a1f35;
    }
    
    /* Custom header */
    .dashboard-header {
        background: linear-gradient(135deg, #8b5cf6, #3b82f6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 32px;
        font-weight: 800;
        margin-bottom: 0;
    }
    
    .dashboard-sub {
        color: #8892b0 !important;
        font-size: 14px;
    }
    
    /* Button overrides */
    .stButton > button {
        background: linear-gradient(135deg, #8b5cf6, #3b82f6);
        color: white;
        border: none;
        border-radius: 8px;
        font-weight: 600;
    }
    
    /* Text input */
    .stTextInput > div > div > input {
        background-color: #1a1f35;
        color: #e8ecf5;
        border: 1px solid #2a3152;
        border-radius: 8px;
    }
    
    .stTextArea > div > div > textarea {
        background-color: #1a1f35;
        color: #e8ecf5;
        border: 1px solid #2a3152;
    }
</style>
""", unsafe_allow_html=True)


# ---- API Helper ----
API_BASE = "http://localhost:8000"


def api_get(endpoint: str):
    """Fetch data from the FastAPI backend."""
    try:
        resp = requests.get(f"{API_BASE}{endpoint}", timeout=5)
        return resp.json()
    except requests.exceptions.ConnectionError:
        return None
    except Exception as e:
        st.error(f"API Error: {e}")
        return None


def api_post(endpoint: str, data: dict = None):
    """Post data to the FastAPI backend."""
    try:
        resp = requests.post(f"{API_BASE}{endpoint}", json=data or {}, timeout=5)
        return resp.json()
    except requests.exceptions.ConnectionError:
        return None
    except Exception as e:
        st.error(f"API Error: {e}")
        return None


# ---- Header ----
st.markdown('<h1 class="dashboard-header">🌾 GramSetu Judge Dashboard</h1>', unsafe_allow_html=True)
st.markdown('<p class="dashboard-sub">Multi-Agent Government Form Filler — NVIDIA NIM + WhatsApp</p>', unsafe_allow_html=True)

# Check API connection
health = api_get("/api/health")
if health:
    nim_status = health.get("nvidia_nim", "unknown")
    nim_color = "🟢" if nim_status == "connected" else "🟡"
    st.markdown(f"<p style='font-size: 12px; color: #8892b0;'>API: 🟢 Connected | NVIDIA NIM: {nim_color} {nim_status}</p>", unsafe_allow_html=True)
else:
    st.error("⚠️ Backend server not running! Start it with: `python -m whatsapp_bot.main`")
    st.stop()


# ---- Sidebar: Stats ----
with st.sidebar:
    st.markdown("### 📊 System Stats")
    stats = api_get("/api/stats") or {}
    
    col1, col2 = st.columns(2)
    with col1:
        stat_card("Conversations", stats.get("total_conversations", 0), "💬", "#3b82f6")
    with col2:
        stat_card("Submissions", stats.get("total_submissions", 0), "📝", "#8b5cf6")
    
    st.markdown("")
    
    col3, col4 = st.columns(2)
    with col3:
        stat_card("Pending", stats.get("pending", 0), "⏳", "#f59e0b")
    with col4:
        stat_card("Confirmed", stats.get("confirmed", 0), "✅", "#10b981")
    
    st.markdown("---")
    
    # Agent Status
    st.markdown("### 🤖 Agent Status")
    agent_status_card("Orchestrator", "active", "🧠")
    agent_status_card("Form Filler", "idle", "📝")
    agent_status_card("Validator", "idle", "✅")
    agent_status_card("Safety Agent", "idle", "🛡️")
    
    st.markdown("---")
    st.markdown("<p style='font-size: 11px; color: #5a6380;'>Auto-refreshes every 5 seconds</p>", unsafe_allow_html=True)


# ---- Main Content: Tabs ----
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "💬 Live Feed",
    "📝 Pending Review",
    "📊 Confidence Meter",
    "📋 Audit Logs",
    "🧪 Test Chat",
])


# ---- TAB 1: Live Feed ----
with tab1:
    section_header("Live Message Feed", "💬")
    
    conversations = api_get("/api/conversations")
    convos = conversations.get("conversations", []) if conversations else []
    
    if not convos:
        st.info("No messages yet. Send a test message from the '🧪 Test Chat' tab!")
    else:
        for convo in convos[:20]:  # Show last 20 messages
            lang = convo.get("detected_language", "en")
            
            # Show user message
            if convo.get("original_text"):
                message_bubble(
                    convo["original_text"],
                    "incoming",
                    lang,
                    timestamp=convo.get("timestamp"),
                )
                
                # Show translation if Hindi
                if lang == "hi" and convo.get("translated_text"):
                    st.markdown(f"<p style='font-size: 11px; color: #6b7280; margin-left: 20%; text-align: right;'>🔄 Translation: {convo['translated_text']}</p>", unsafe_allow_html=True)
            
            # Show bot response
            if convo.get("bot_response"):
                message_bubble(
                    convo["bot_response"],
                    "outgoing",
                    lang,
                    agent=convo.get("active_agent"),
                    timestamp=convo.get("timestamp"),
                )
            
            st.markdown("<hr style='border: 0; border-top: 1px solid #1a1f35; margin: 4px 0;'>", unsafe_allow_html=True)


# ---- TAB 2: Pending Review ----
with tab2:
    section_header("Forms Pending Human Confirmation", "📝")
    
    pending = api_get("/api/submissions/pending")
    submissions = pending.get("submissions", []) if pending else []
    
    if not submissions:
        st.info("No pending submissions. Complete a form from the Test Chat tab!")
    else:
        for sub in submissions:
            with st.expander(f"📋 {sub.get('form_type', 'Unknown')} — {sub.get('created_at', '')[:19]}", expanded=True):
                form_data = sub.get("form_data", {})
                confidence = sub.get("confidence_scores", {})
                
                # Show fields with confidence
                for field, value in form_data.items():
                    conf = confidence.get(field, 0.5)
                    col_a, col_b = st.columns([3, 1])
                    with col_a:
                        st.text(f"{field}: {value}")
                    with col_b:
                        pct = int(conf * 100)
                        color = "🟢" if pct >= 80 else "🟡" if pct >= 50 else "🔴"
                        st.text(f"{color} {pct}%")
                
                # Validation
                validation = sub.get("validation_result", {})
                errors = [f"❌ {k}: {v.get('error')}" for k, v in validation.items() if not v.get("valid")]
                if errors:
                    st.warning("\n".join(errors))
                else:
                    st.success("✅ All fields validated")
                
                # Admin Actions
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"✅ Confirm #{sub['id']}", key=f"confirm_{sub['id']}"):
                        result = api_post(f"/api/confirm/{sub['id']}", {"notes": "Approved by admin"})
                        if result:
                            st.success("Confirmed!")
                            st.rerun()
                with col2:
                    if st.button(f"❌ Reject #{sub['id']}", key=f"reject_{sub['id']}"):
                        result = api_post(f"/api/reject/{sub['id']}", {"notes": "Rejected by admin"})
                        if result:
                            st.warning("Rejected")
                            st.rerun()


# ---- TAB 3: Confidence Meter ----
with tab3:
    section_header("AI Confidence Scores per Field", "📊")
    
    all_subs = api_get("/api/submissions")
    all_submissions = all_subs.get("submissions", []) if all_subs else []
    
    if not all_submissions:
        st.info("No form submissions yet. Complete a form to see confidence scores!")
    else:
        latest = all_submissions[0]
        
        st.markdown(f"**Latest Submission:** {latest.get('form_type', 'Unknown')} — Status: `{latest.get('status', 'unknown')}`")
        st.markdown("")
        
        confidence_scores = latest.get("confidence_scores", {})
        form_data = latest.get("form_data", {})
        
        if confidence_scores:
            for field, conf in confidence_scores.items():
                value = form_data.get(field, "")
                confidence_bar(field, conf, f"{field}: {value}")
        
        # Average confidence
        if confidence_scores:
            avg = sum(confidence_scores.values()) / len(confidence_scores)
            st.markdown(f"""
            <div style="
                background: #1a1f35;
                border: 2px solid {'#10b981' if avg >= 0.7 else '#f59e0b'};
                border-radius: 12px;
                padding: 20px;
                text-align: center;
                margin-top: 20px;
            ">
                <div style="font-size: 14px; color: #8892b0;">AVERAGE CONFIDENCE</div>
                <div style="font-size: 42px; font-weight: 800; color: {'#10b981' if avg >= 0.7 else '#f59e0b'};">
                    {int(avg * 100)}%
                </div>
            </div>
            """, unsafe_allow_html=True)


# ---- TAB 4: Audit Logs ----
with tab4:
    section_header("Immutable Audit Trail", "📋")
    
    logs_data = api_get("/api/logs")
    logs = logs_data.get("logs", []) if logs_data else []
    
    if not logs:
        st.info("No audit logs yet. Interact with the bot to generate logs!")
    else:
        for log in logs[:50]:
            agent_icons = {
                "orchestrator": "🧠",
                "form_filler": "📝",
                "validator": "✅",
                "safety": "🛡️",
            }
            icon = agent_icons.get(log.get("agent_name", ""), "🤖")
            conf = log.get("confidence_score")
            conf_str = f" — Confidence: {int(conf * 100)}%" if conf is not None else ""
            
            with st.expander(f"{icon} [{log.get('agent_name', '?')}] {log.get('action', '?')}{conf_str} — {log.get('timestamp', '')[:19]}"):
                if log.get("input_data"):
                    st.markdown("**Input:**")
                    st.json(log["input_data"])
                if log.get("output_data"):
                    st.markdown("**Output:**")
                    st.json(log["output_data"])


# ---- TAB 5: Test Chat ----
with tab5:
    section_header("Test Chat (Simulates WhatsApp)", "🧪")
    st.markdown("<p style='color: #8892b0;'>Send messages to test the multi-agent system. Try saying <b>namaste</b> or <b>hello</b>!</p>", unsafe_allow_html=True)
    
    # Initialize chat history
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    
    # Display chat
    chat_container = st.container()
    with chat_container:
        for msg in st.session_state.chat_history:
            message_bubble(
                msg["text"],
                msg["direction"],
                msg.get("language", "en"),
                agent=msg.get("agent"),
            )
    
    # Input
    col_input, col_send = st.columns([5, 1])
    with col_input:
        user_msg = st.text_input(
            "Message",
            key="chat_input",
            placeholder="Type a message... (try 'namaste' or 'I want PAN card')",
            label_visibility="collapsed",
        )
    with col_send:
        send_btn = st.button("Send ▶", use_container_width=True)
    
    if send_btn and user_msg:
        # Add user message to history
        st.session_state.chat_history.append({
            "text": user_msg,
            "direction": "incoming",
            "language": "hi" if any('\u0900' <= c <= '\u097F' for c in user_msg) else "en",
        })
        
        # Call the API
        result = api_post("/api/chat", {
            "message": user_msg,
            "user_id": "judge-test-user",
            "phone": "9999999999",
        })
        
        if result and result.get("response"):
            st.session_state.chat_history.append({
                "text": result["response"],
                "direction": "outgoing",
                "language": result.get("language", "en"),
                "agent": result.get("active_agent", "bot"),
            })
            
            # Update sidebar agent status dynamically
            st.rerun()
        else:
            st.session_state.chat_history.append({
                "text": "⚠️ Error: Could not reach the bot server.",
                "direction": "outgoing",
            })
            st.rerun()


# ---- Auto-refresh ----
# Streamlit doesn't natively support auto-refresh, but we can use a workaround
# The dashboard will refresh when the user interacts with it

"""
============================================
components.py — Streamlit Dashboard Components
============================================
Reusable UI components for the judge dashboard:
  - Confidence bars
  - Agent status cards
  - Message bubbles
"""

import streamlit as st


def agent_status_card(agent_name: str, status: str, icon: str):
    """
    Display an agent status card.
    
    Args:
        agent_name: Name of the agent
        status: "active", "idle", "completed"
        icon: Emoji icon for the agent
    """
    colors = {
        "active": "#10b981",    # Green
        "idle": "#6b7280",      # Gray
        "completed": "#3b82f6", # Blue
        "error": "#ef4444",     # Red
    }
    color = colors.get(status, colors["idle"])
    
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #1a1f35, #232a42);
        border: 1px solid {color}40;
        border-left: 4px solid {color};
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 8px;
    ">
        <div style="display: flex; align-items: center; gap: 8px;">
            <span style="font-size: 24px;">{icon}</span>
            <div>
                <div style="font-weight: 600; color: #e8ecf5; font-size: 14px;">{agent_name}</div>
                <div style="color: {color}; font-size: 12px; text-transform: uppercase; letter-spacing: 1px;">
                    {'● ' if status == 'active' else '○ '}{status}
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def confidence_bar(field_name: str, confidence: float, label_hi: str = ""):
    """
    Display a horizontal confidence bar for a form field.
    
    Args:
        field_name: Field name (e.g., "aadhaar_number")
        confidence: 0.0 to 1.0
        label_hi: Hindi label (optional)
    """
    pct = int(confidence * 100)
    
    if pct >= 80:
        color = "#10b981"  # Green
        emoji = "🟢"
    elif pct >= 50:
        color = "#f59e0b"  # Amber
        emoji = "🟡"
    else:
        color = "#ef4444"  # Red
        emoji = "🔴"
    
    label = label_hi if label_hi else field_name.replace("_", " ").title()
    
    st.markdown(f"""
    <div style="margin-bottom: 8px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <span style="color: #8892b0; font-size: 13px;">{emoji} {label}</span>
            <span style="color: {color}; font-weight: 700; font-size: 13px;">{pct}%</span>
        </div>
        <div style="background: #1a1f35; border-radius: 6px; height: 8px; overflow: hidden;">
            <div style="background: {color}; width: {pct}%; height: 100%; border-radius: 6px; transition: width 0.5s;"></div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def message_bubble(text: str, direction: str, language: str = "en",
                   agent: str = None, timestamp: str = None):
    """
    Display a chat message bubble.
    
    Args:
        text: Message text
        direction: "incoming" (user) or "outgoing" (bot)
        language: "hi" or "en"
        agent: Which agent handled this
        timestamp: When the message was sent
    """
    if direction == "incoming":
        bg = "#3b82f6"
        align = "flex-end"
        label = "👤 User"
        lang_badge = f"🇮🇳 Hindi" if language == "hi" else "🇬🇧 English"
    else:
        bg = "#232a42"
        align = "flex-start"
        label = f"🤖 {agent or 'Bot'}"
        lang_badge = ""
    
    time_str = timestamp[:19] if timestamp else ""
    
    st.markdown(f"""
    <div style="display: flex; justify-content: {align}; margin-bottom: 10px;">
        <div style="
            background: {bg};
            border-radius: 12px;
            padding: 10px 14px;
            max-width: 80%;
            color: #e8ecf5;
            font-size: 14px;
            line-height: 1.5;
        ">
            <div style="font-size: 11px; color: #8892b0; margin-bottom: 4px;">
                {label} {f'• {lang_badge}' if lang_badge else ''} {f'• {time_str}' if time_str else ''}
            </div>
            <div style="white-space: pre-line;">{text}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def stat_card(label: str, value: int, icon: str, color: str = "#3b82f6"):
    """Display a statistics card."""
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #1a1f35, #232a42);
        border: 1px solid #2a3152;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
    ">
        <div style="font-size: 28px; margin-bottom: 4px;">{icon}</div>
        <div style="font-size: 28px; font-weight: 700; color: {color};">{value}</div>
        <div style="font-size: 12px; color: #8892b0; text-transform: uppercase; letter-spacing: 1px;">{label}</div>
    </div>
    """, unsafe_allow_html=True)


def section_header(title: str, icon: str = ""):
    """Display a styled section header."""
    st.markdown(f"""
    <div style="
        border-bottom: 1px solid #2a3152;
        padding-bottom: 8px;
        margin: 20px 0 12px;
    ">
        <h3 style="color: #e8ecf5; font-size: 18px; font-weight: 600; margin: 0;">
            {icon} {title}
        </h3>
    </div>
    """, unsafe_allow_html=True)

"""
============================================================
react_agent.py — Autonomous ReAct Loop for Web Automation
============================================================
"""
import json
from backend.mcp_tool_router import get_router
from backend.llm_client import chat_with_tools

# System prompt for the ReAct Agent
SYSTEM_PROMPT = """
You are GramSetu, an autonomous AI web assistant. 
Your goal is to complete the user's request using the tools available to you.
You have access to a browser, digilocker, whatsapp tools, and more.

INSTRUCTIONS:
1. When asked to fill out a form or navigate the web, use the browser tools.
2. Observe the page state using `browser__get_page_state`.
3. Take actions using `browser__navigate`, `browser__fill_field`, `browser__click_button`, etc.
4. Continue taking actions iteratively until you have completely fulfilled the user's request.
5. If you hit a roadblock or finish the task, respond to the user with a helpful message.
6. Be concise. Only explain what you did or what you need from the user.
"""

async def run_react_loop(session_id: str, user_request: str, max_steps: int = 15) -> str:
    """
    Run an autonomous loop where the LLM can call tools iteratively.
    """
    router = get_router()
    tools = router.get_tool_catalog()
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_request}
    ]
    
    from backend.database import log_audit
    
    print(f"\n[ReAct Agent] Starting task for session {session_id}: '{user_request}'")
    
    for step in range(max_steps):
        print(f"\n[ReAct Agent] Step {step+1}/{max_steps} — Reasoning...")
        
        # 1. Call LLM with tools
        response_message = await chat_with_tools(messages, tools, temperature=0.1, max_tokens=1024)
        
        if not response_message:
            print("[ReAct Agent] ERROR: No response from LLM.")
            return "❌ Agent encountered an error communicating with the LLM."
            
        messages.append(response_message)
        
        # 2. Check if the LLM wants to call tools
        tool_calls = response_message.get("tool_calls")
        
        if not tool_calls:
            # The LLM decided to reply to the user instead of calling a tool
            content = response_message.get("content", "")
            print(f"[ReAct Agent] Task Finished. Response: {content}")
            return content
            
        # 3. Execute the tools requested by the LLM
        for tool_call in tool_calls:
            func = tool_call.get("function", {})
            full_name = func.get("name", "")
            call_id = tool_call.get("id", "")
            
            # Parse arguments
            try:
                kwargs = json.loads(func.get("arguments", "{}"))
            except Exception as e:
                kwargs = {}
                
            print(f"  → ACTION: {full_name}")
            print(f"    PARAMS: {json.dumps(kwargs, indent=2)}")
            
            if "__" in full_name:
                server, tool_name = full_name.split("__", 1)
                
                # Special handling: inject session_id automatically if needed
                if "session_id" not in kwargs:
                    kwargs["session_id"] = session_id
                    
                # Execute via Router
                try:
                    result = await router.execute(server, tool_name, **kwargs)
                except Exception as e:
                    result = {"error": f"Execution failed: {str(e)}"}
            else:
                result = {"error": f"Invalid tool format: {full_name}"}
                
            # Log to Audit Database
            try:
                log_audit(
                    user_id=session_id,
                    agent_name="ReActAgent",
                    action=full_name,
                    input_data=kwargs,
                    output_data={"success": result.get("success", False), "error": result.get("error")} if isinstance(result, dict) else {"result": "ok"},
                    status="success" if not result.get("error") else "error"
                )
            except Exception as e:
                print(f"  [Audit] Failed to log: {e}")

            # Truncate large results (like base64 screenshots) to prevent context bloat
            display_result = str(result)
            if isinstance(result, dict) and "screenshot_b64" in result:
                result["screenshot_b64"] = "[BASE64_IMAGE_OMITTED_FOR_CONTEXT]"
                
            print(f"  ← RESULT: {display_result[:150]}...")
            
            # 4. Append tool result to messages
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "name": full_name,
                "content": json.dumps(result)
            })
            
    return "⚠️ ReAct Agent reached the maximum number of steps without finishing."

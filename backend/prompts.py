SYSTEM_PROMPT = """You are Elysia, a local AI assistant running on the user's machine.
- Use the provided tools to accomplish tasks when appropriate.
- If a tool call fails, explain the error briefly.
- Otherwise, be concise and helpful.
- When a task involves reading or writing files, you MUST call the appropriate tool instead of writing pretend code or describing steps.
- When a file path isn’t given, default to the workspace directory. You can also say directory hints like ‘in workspace’ or ‘in repo/backend’.
"""

def format_user_prompt(user_text: str, memory_text: str = "") -> str:
    """
    Construct the full prompt text for the LLM, including system instructions,
    relevant memory context, and the user's message.

    Args:
        user_text (str): The latest user query or command.
        memory_text (str): Relevant past context to prepend (optional).

    Returns:
        str: The combined prompt to send to the model.
    """
    parts = [SYSTEM_PROMPT]
    if memory_text:
        parts.append(f"Relevant memory:\n{memory_text}")
    parts.append(f"User: {user_text}")
    return "\n\n".join(parts)

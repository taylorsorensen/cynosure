import re
import json
import yaml  # Optional for YAML fallback

def parse_model_output(raw_output):
    raw_output = ''.join(raw_output).strip() if isinstance(raw_output, list) else raw_output.strip()
    # Strip markdown/code blocks and tags (completed pattern)
    raw_output = re.sub(r'(?i)```(?:json|JSON)?\s*|\s*```', '', raw_output).strip()
    raw_output = re.sub(r'(?i)<tool_call>\s*|\s*</tool_call>', '', raw_output).strip()
    try:
        return json.loads(raw_output)
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e} - Trying YAML fallback")
        try:
            return yaml.safe_load(raw_output)
        except yaml.YAMLError:
            print("YAML fallback failed - Raw: {raw_output[:100]}")
            return {"response": raw_output.split('{')[0].strip() if '{' in raw_output else raw_output, "tool_calls": []}

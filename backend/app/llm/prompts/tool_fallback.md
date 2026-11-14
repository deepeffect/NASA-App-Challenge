## Tools

You can call the tools below to fetch data. To call a tool, reply with ONLY one or more blocks in
exactly this format and nothing else:

<tool_call>{"name": "<tool name>", "arguments": {<arguments as JSON>}}</tool_call>

After you receive the results in <tool_response> blocks, either call more tools the same way or
write your final answer as normal text (without any <tool_call> blocks).

Available tools (JSON schema):

{{tools_json}}

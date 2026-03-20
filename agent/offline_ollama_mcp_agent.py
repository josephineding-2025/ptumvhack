import argparse
import asyncio
import inspect
import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from agent.prompts import MISSION_ySTART_PROMPT, SYSTEM_PROMPT, user_command_prompt


@dataclass
class OfflineAgentConfig:
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3:8b")
    mcp_command: str = os.getenv("MCP_COMMAND", "python")
    mcp_args: tuple[str, ...] = tuple(
        os.getenv("MCP_ARGS", "-m server.fastmcp_bridge").split()
    )


async def _load_tools(client: MultiServerMCPClient) -> tuple[Any, bool]:
    enter = getattr(client, "__aenter__", None)
    if enter and inspect.iscoroutinefunction(enter):
        await client.__aenter__()
        tools = await client.get_tools()
        return tools, True
    tools = await client.get_tools()
    return tools, False


async def run_agent(command: str) -> dict[str, Any]:
    config = OfflineAgentConfig()

    client = MultiServerMCPClient(
        {
            "drone_promax": {
                "transport": "stdio",
                "command": config.mcp_command,
                "args": list(config.mcp_args),
            }
        }
    )

    tools, entered = await _load_tools(client)
    try:
        llm = ChatOpenAI(
            model=config.ollama_model,
            base_url=config.ollama_base_url,
            api_key="ollama",
            temperature=0,
        )

        agent = create_react_agent(llm, tools, prompt=SYSTEM_PROMPT)
        mission_prompt = (
            f"{MISSION_START_PROMPT}\n\n"
            f"{user_command_prompt(command)}\n"
            "Use available MCP tools immediately and return a concise action summary."
        )
        return await agent.ainvoke({"messages": [("user", mission_prompt)]})
    finally:
        if entered:
            await client.__aexit__(None, None, None)


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Run drone promax with local Ollama model through MCP (offline-first)."
    )
    parser.add_argument(
        "--command",
        default="Scan the map, prioritize high coverage, and report survivors.",
        help="Mission command for the agent.",
    )
    args = parser.parse_args()

    result = asyncio.run(run_agent(args.command))
    print(result)


if __name__ == "__main__":
    main()

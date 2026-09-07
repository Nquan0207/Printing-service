"""Run inside either MCP container: python - < docker/check-mcp.py."""
import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    module = os.environ.get('MCP_CHECK_MODULE', 'stockroom_shop.server')
    expected = 'get_dashboard' if module.startswith('stockroom_ops') else 'list_categories'
    params = StdioServerParameters(command=sys.executable,
                                  args=['-m', module, '--transport', 'stdio'], env=dict(os.environ))
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert expected in {tool.name for tool in tools.tools}
            result = await session.call_tool(expected, {})
            assert not getattr(result, "isError", getattr(result, "is_error", False)), result
            resources = await session.list_resources()
            assert resources.resources
            view = await session.read_resource(resources.resources[0].uri)
            assert view.contents
            print(f'{module}: stdio initialize, tools/call, resources/read passed')

asyncio.run(main())

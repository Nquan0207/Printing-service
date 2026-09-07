import asyncio
import os

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

pytestmark = pytest.mark.skipif(os.getenv('DOCKER_MCP_E2E') != '1', reason='Docker MCP integration only')


@pytest.mark.parametrize('url,tool', [('http://mcp:3001/mcp', 'get_dashboard'),
                                     ('http://shopping-mcp:3003/mcp', 'list_categories')])
def test_http_mcp_tools_and_views(url, tool):
    async def check():
        async with streamable_http_client(url) as (reader, writer, _):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                listed = await session.list_tools()
                assert tool in {item.name for item in listed.tools}
                result = await session.call_tool(tool, {})
                assert not result.isError, result
                resources = await session.list_resources()
                assert resources.resources
                resource = await session.read_resource(resources.resources[0].uri)
                assert resource.contents
    asyncio.run(check())


def test_web_and_product_image():
    with httpx.Client(timeout=15) as client:
        web = client.get('http://web:8080/')
        assert web.status_code == 200 and '<div id="root">' in web.text
        catalog = client.get('http://web:8080/api/v1/products?limit=1').json()
        product = catalog['groups'][0]['products'][0]
        assert product['images']
        image = client.get('http://web:8080' + product['images'][0])
        assert image.status_code == 200
        assert image.headers['content-type'].startswith('image/')

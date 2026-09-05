from app.mcp_server.server import mcp
from app.mcp_server.storefront_widget import STOREFRONT_HTML, STOREFRONT_URI


def test_storefront_tools_and_resource_are_registered():
    tools = {tool.name: tool for tool in mcp._tool_manager.list_tools()}
    expected = {
        "open_storefront",
        "mock_sign_in",
        "get_mock_session",
        "create_cart",
        "get_cart",
        "add_cart_item",
        "update_cart_item",
        "remove_cart_item",
        "create_mock_checkout",
        "decide_mock_payment",
        "get_mock_order",
    }
    assert expected <= tools.keys()
    assert tools["open_storefront"].meta["ui"]["resourceUri"] == STOREFRONT_URI
    assert tools["open_storefront"].annotations.readOnlyHint is True
    assert tools["add_cart_item"].annotations.readOnlyHint is False
    assert tools["decide_mock_payment"].meta["openai/widgetAccessible"] is True
    assert "confirmation_token" in tools["decide_mock_payment"].fn_metadata.arg_model.model_fields
    assert "session_id" in tools["create_cart"].fn_metadata.arg_model.model_fields

    resources = {str(resource.uri): resource for resource in mcp._resource_manager.list_resources()}
    assert STOREFRONT_URI in resources
    assert resources[STOREFRONT_URI].mime_type == "text/html;profile=mcp-app"


def test_storefront_widget_contains_mock_checkout_and_bridge_controls():
    assert "tools/call" in STOREFRONT_HTML
    assert "ui/initialize" in STOREFRONT_HTML
    assert "Approve mock payment" in STOREFRONT_HTML
    assert "Reject mock payment" in STOREFRONT_HTML
    assert "No password, card details, or real payment" in STOREFRONT_HTML
    assert "Mock sign in" in STOREFRONT_HTML
    assert "Mock receipt" in STOREFRONT_HTML
    assert "supplier website opens" in STOREFRONT_HTML
    assert "requestCheckout" not in STOREFRONT_HTML


def test_customer_facing_product_payload_hides_supplier_url(monkeypatch):
    from app.mcp_server import tools as tool_handlers

    class Product:
        id = 1; source_product_id = "x"; name = "Mock"; brand = None; price_jpy = 100
        description = None; colors = []; sizes = []; stock_status = None
        printing_available = None; product_url = "https://supplier.example/product"
        image_url = None; scraped_at = None
        category = type("Category", (), {"slug": "c", "name": "C", "industry": type("Industry", (), {"slug": "i", "name": "I"})()})()

    payload = tool_handlers._product_payload(Product())
    assert "product_url" not in payload
    assert "supplier.example" not in str(payload)

from .client import HttpClient
from .parser import NormalizedProduct, parse_product


def crawl_product(client: HttpClient, url: str, industry: str, category: str) -> NormalizedProduct:
    return parse_product(client.get_text(url, delayed=True), url, industry, category)


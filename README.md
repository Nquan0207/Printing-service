# RAKSUL Product Catalog MVP

> **Note:** this documents the earlier *apparel* MVP in [app/](app/), which targets
> apparel.raksul.com and its own `raksul_db`. The active work is the stockroom
> PoC — see [crawler/README.md](crawler/README.md) for the crawler and
> [docs/requirement.md](docs/requirement.md) for the spec. `docker compose up -d`
> now provisions the **`stockroom`** database and MinIO, not `raksul_db`.

Một repository tự chứa toàn bộ luồng Stockroom:

```text
stockroom.raksul.com
        │ offline crawl
        ▼
PostgreSQL + private MinIO
        │
        ▼
Go API (127.0.0.1:8080)
        │
        ▼
Python MCP + embedded widget
```

Crawler là bước nhập dữ liệu offline. Khi chạy storefront, MCP chỉ gọi Go API;
nó không truy cập website nhà cung cấp và không chạy SQL trực tiếp. Checkout là
mô phỏng, không có thanh toán thật.

## Thành phần

- `stockroom_crawler/`: discovery, parser, PostgreSQL upsert và lưu ảnh MinIO.
- `go-backend/`: API catalog, quote, demo users, cart, mock orders và media proxy.
- `app/mcp_server/`: MCP tools và widget nhúng.
- `docs/api-contract.yaml`: contract giữa MCP và Go API.
- `legacy/`: crawler SQLAlchemy cũ, chỉ lưu tham khảo và không nằm trong test mặc định.

PostgreSQL dùng database `stockroom` với các bảng `users`, `categories`,
`products`, `product_images`, `product_sizes`, `cart_items`, `orders`
và `order_items`.

## Yêu cầu

- Python 3.11+
- Docker Desktop với Docker Compose
- `make` và `curl`

Go được build/test trong container, nên không bắt buộc cài Go trên máy.

## Thiết lập sạch lần đầu

Tạo môi trường Python:

```bash
make setup
```

Sao chép cấu hình mẫu nếu chưa có `.env`:

```bash
cp .env.example .env
```

Lệnh sau **xóa toàn bộ volume PostgreSQL và MinIO của project**, sau đó tạo lại
schema Stockroom:

```bash
make reset-db CONFIRM_RESET=1
```

Kiểm tra crawler bằng bộ dữ liệu nhỏ, sau đó crawl theo giới hạn trong `.env`:

```bash
make crawl-smoke
make crawl
```

Crawler dùng UPSERT cho category, product và size. Size S/M/L được cập nhật tại
chỗ để ID không đổi khi crawl lại; danh sách ảnh trong database được đồng bộ với
lần crawl mới nhất.

Build và bật Go API:

```bash
make api
make health
```

Chạy MCP qua stdio:

```bash
make mcp
```

Hoặc Streamable HTTP tại `http://127.0.0.1:8000/mcp`:

```bash
make mcp-http
```

## Chat app local với Ollama

Chat app tại `http://127.0.0.1:3000` là một MCP host riêng: Ollama chọn tool,
chat backend gọi MCP qua stdio, và MCP tiếp tục gọi Go API. Mỗi browser session
có MCP process, demo user và conversation riêng. `place_order` không được đưa
cho model; chỉ nút Approve/Reject sau bước review mới gọi tool đó.

Cài và tải model một lần:

```bash
brew install ollama
ollama serve
```

Trong terminal khác:

```bash
make ollama-pull
make api
make health
make chat
```

Mở `http://127.0.0.1:3000`, đăng nhập demo bằng name/email rồi chat bằng tiếng
Việt hoặc tiếng Anh. Đây không phải xác thực thật và checkout không di chuyển
tiền. Không chạy `make mcp` hoặc `make mcp-http` cùng chat app vì chat app tự
khởi chạy MCP stdio cho từng session.

Kiểm tra cả Ollama và Go API từ chat host:

```bash
make chat-health
```

Khi Go API, Ollama và chat app đều đang chạy, kiểm tra toàn bộ vòng
Ollama → MCP tool → Go API bằng:

```bash
make test-chat-e2e
```

## Lệnh thường dùng

```bash
make infra         # PostgreSQL + MinIO
make stats         # số row catalog
make crawl-smoke   # 3 sản phẩm, 1 category
make crawl         # dùng giới hạn trong .env
make api           # build/start Go API
make health        # health PostgreSQL + MinIO qua API
make ollama-pull   # tải model OLLAMA_MODEL, mặc định qwen3:8b
make chat          # chat UI tại 127.0.0.1:3000
make chat-health   # health Go API + Ollama qua chat host
make test-chat-e2e # smoke test thật qua Ollama + MCP; yêu cầu chat đang chạy
make test          # Python unit tests + Go compile/tests trong container
make test-e2e      # API round trip; yêu cầu API và catalog đang chạy
```

Có thể gọi crawler trực tiếp bằng cùng virtualenv ở root:

```bash
./.venv/bin/python -m stockroom_crawler.cli categories
./.venv/bin/python -m stockroom_crawler.cli init-db
./.venv/bin/python -m stockroom_crawler.cli crawl --category store_supplies --limit 5
./.venv/bin/python -m stockroom_crawler.cli stats
```

`init-db` drop toàn bộ bảng commerce trước khi tạo lại. Chỉ dùng trên môi
trường được phép mất dữ liệu; workflow khuyến nghị là target `reset-db` có cờ
xác nhận.

## Kiểm tra end-to-end

Sau `make crawl-smoke && make api`:

```bash
make test-e2e
```

Test thực hiện health check, tìm một sản phẩm, đăng nhập demo, quote, thêm cart,
tạo mock order và đọc lại order. Test có ghi dữ liệu demo vào local database.

## MCP và plugin local

MCP mặc định gọi `http://127.0.0.1:8080`. Plugin local đã cấu hình trong
`plugins/raksul-catalog/.mcp.json` để chạy:

```bash
./.venv/bin/python -m app.mcp_server.server
```

Widget hỗ trợ chọn/tạo demo user, tìm sản phẩm, chọn size, quote, cart và bước
xác nhận mock order trong 15 phút. Go API tin header `X-Stockroom-User`, vì
vậy API chỉ được bind loopback và không được publish trực tiếp ra Internet.

### Cập nhật plugin sau khi sửa MCP hoặc widget

Khi thay đổi tool name/schema/annotations, widget HTML/CSS/JavaScript,
`ui://` resource, `.mcp.json` hoặc `plugin.json`, cập nhật cachebuster rồi cài
lại plugin local:

```bash
python3 ~/.codex/skills/.system/plugin-creator/scripts/update_plugin_cachebuster.py \
  "$(pwd)/plugins/raksul-catalog"

/opt/homebrew/bin/codex plugin add \
  raksul-catalog@raksul-printing
```

Sau đó thoát hoàn toàn ChatGPT Desktop, mở lại và tạo chat mới. Không cần chạy
hai lệnh này khi chỉ crawl thêm dữ liệu hoặc cập nhật dữ liệu PostgreSQL/MinIO.

## Cấu hình

Các biến đầy đủ nằm trong `.env.example`:

- `STOCKROOM_DATABASE_URL` và `MINIO_*` cho crawler chạy trên host.
- `CRAWL_*` cho giới hạn, số ảnh và delay.
- `STOCKROOM_API_URL` cho MCP.
- `MCP_HOST`, `MCP_PORT`, `MCP_TRANSPORT` cho MCP server.
- `OLLAMA_URL`, `OLLAMA_MODEL` và `CHAT_*` cho local chat host.

Docker Compose sử dụng hostname nội bộ `postgres` và `minio`; không thay các
URL đó bằng địa chỉ host.

make infra
make crawl
make api
make health
make mcp
make mcp-http
make ollama-pull
make chat
make chat-health
make test-chat-e2e
make test
make test-e2e

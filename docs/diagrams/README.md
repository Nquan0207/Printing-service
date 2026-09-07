# Diagrams

Mermaid source plus rendered PNGs. The `.mmd` files are the originals — edit
those and re-render; never hand-edit a PNG.

| File | What it shows |
|---|---|
| [erd.mmd](erd.mmd) · [png](erd.png) | Database ERD, from [backend-ops/schema.sql](../../backend-ops/schema.sql) |
| [read-flow.mmd](read-flow.mmd) · [png](read-flow.png) | Admin prompt → answer, including the panel refining itself without the model |
| [architecture.mmd](architecture.mmd) · [png](architecture.png) | The five services and every path between them |

## Regenerating

```bash
cd frontend-ops && node render-mermaid.mjs
```

It renders every `.mmd` in this directory to a PNG beside it, using the local
`mermaid` package and the same system Chrome as `render-check.mjs`. Deliberately
**not** `@mermaid-js/mermaid-cli`, which downloads its own chromium.

Each diagram is drawn at its natural size and captured at 2×. Mermaid caps the
`<svg>` with a `max-width`, so without overriding it first a scale factor only
upscales a 300 px render.

## The semicolon trap

**`;` is a statement separator in mermaid.** A label containing one — the MIME
type `text/html;profile=mcp-app` is the obvious candidate here — fails to parse
with a message pointing at the *next* line, which is thoroughly misleading. It
has bitten this repo twice, in [flow.md](../flow.md) and in `read-flow.mmd`.
Write it as `MIME text/html profile=mcp-app` instead.

# Product Similarity Search API (FAISS + CLIP)

This API provides image/text similarity search over your existing MySQL `products` table. It stores only a FAISS index and a mapping; no new tables are created. Paths are relative to the project root.

## Quick Start
- Activate venv and install:
  ```
  python -m venv venv
  venv\Scripts\activate
  pip install -r ./requirements.txt
  ```
- Configure environment in `./.env`:
  ```
  MYSQL_URL=mysql://<user>:<pass>@<host>:<port>/<database>
  EMBEDDING_MODEL=clip-ViT-B-32
  EMBED_SOURCE=auto
  ```
- Start the server:
  ```
  python -m faiss_api.app
  ```
- Health check:
  ```
  GET /health
  ```
  Returns `{ index_ready, index_size, progress, error }`. Routes return `503` with `{"error":"index initializing"}` until the index is ready.

## Frontend Integration
You can call `/search` from any frontend (React/Vue/Next/etc.) Base URL for service is https://steadfastsearchmodel-production.up.railway.app Example using `fetch`:
```js
async function searchProducts(query, topK = 5) {
  const res = await fetch("http://<server>:9990/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Search failed");
  return data.results; // array of full product rows + _similarity
}
```
- Use an image URL for best results: `query = "https://.../product.jpg"`
- Fallback to text queries: `query = "Nordic chandelier metal & glass"`

### What `_similarity` Means
- `_similarity` is the cosine similarity between the query embedding and product embedding (range ~0.0–1.0).
- Values ≥ 0.7 indicate strong visual/textual similarity (near-duplicates or very close matches).
- It is computed using FAISS `IndexFlatIP` with L2-normalized embeddings.

## Data Rules
- The system builds its index from:
  1. MySQL `products` table (if `MYSQL_URL` is set), or
  2. `./product_details.sql` INSERT rows (fallback)
- If `is_deleted` is `1`, the product is skipped and not added to the index.

## API Routes
### `POST /search`
- Input: `{ "query": "<image URL or text>", "top_k": 5 }`
- Output: `{ "results": [<full product row with _similarity>], "count": N }`
- Returns `503` until the index is ready. Use `/health` to check readiness.

### `POST /add-product/<product_id>`
- Fetches the product from MySQL by `product_id`, embeds it, and adds to FAISS.
- Skips products with `is_deleted = 1`.
- Output: `{ "status": "added", "product_id": <id> }` or error if not found/deleted.

### `POST /delete-product/<product_id>`
- Removes the product from the FAISS index by rebuilding without it.
- Output: `{ "status": "deleted", "product_id": <id> }`

### `GET /health`
- Output: `{ "status": "ok", "index_ready": bool, "index_size": number, "progress": { total, processed }, "error": string }`

## Embeddings & Models
- Default model: `clip-ViT-B-32` for balanced speed/accuracy.
- Configure via env:
  - `EMBEDDING_MODEL` to choose CLIP variant (e.g., `clip-ViT-L-14` for higher accuracy, heavier)
  - `EMBED_SOURCE`:
    - `auto` (default): try image URL first; fallback to text
    - `image`: use image URLs only
    - `text`: use `name + description` only

## Persistence
- FAISS index file: `./data/products_index.bin`
- Mapping file: `./data/mapping.json`
- Delete these files to force a rebuild (e.g., after changing models or `EMBED_SOURCE`).

## Production Notes
- Use Gunicorn to run in production:
  ```
  gunicorn faiss_api.app:create_app -b 0.0.0.0:9990 --workers 1 --threads 8 --timeout 180
  ```
- Ensure port `9990/tcp` is open on your firewall/security groups.
- First run downloads the model; it can take time on CPU. Health will report progress.

## CORS
- Allowed origins:
  - `http://localhost:3000`
  - `http://localhost:3001`
  - `https://steadfast.ng`
  - `https://admin.steadfast.ng`
  - `https://padi.steadfast.ng`
- Already enabled via `flask-cors` in the app

## Error Handling
- `503` while index builds: poll `/health` until `index_ready: true`.
- Image fetch failures: queries fallback to text embedding when images are unreachable.
- Dimension mismatch: deleting the index files and restarting rebuilds with the active model.

## Example Response
```json
{
  "results": [
    {
      "id": 223,
      "name": "5 HEADS 1000mm Nordic Led Chandelier METAL & GLASS.",
      "image_urls": ["https://.../product.jpeg"],
      "_similarity": 0.82
    }
  ],
  "count": 1
}
```

# Financial Data MCP Server

Plug finance data (FX, crypto, personal spending insights) into AI agents using MCP.

## V1 Tools

1. `convert_currency`
2. `get_crypto_price`
3. `list_transactions`
4. `get_spending_summary`
5. `flag_anomalies`

## Tech Stack

- Python
- MCP Python SDK
- FastAPI (health endpoint)
- Public APIs:
  - ExchangeRate API: `https://open.er-api.com/v6/latest/{BASE}`
  - CoinGecko Simple Price: `https://api.coingecko.com/api/v3/simple/price`

## Project Layout

- `app/main.py` - MCP tool registration and app bootstrap
- `app/tools/currency.py` - FX conversion logic
- `app/tools/crypto.py` - crypto quote lookup
- `app/tools/transactions.py` - seeded transaction analysis
- `app/data/transactions_seed.json` - local mock transaction dataset
- `tests/` - baseline tests for tool behavior and error paths

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

### Start MCP server (stdio transport)

```bash
python -m app.main
```

### Optional: FastAPI health endpoint

```bash
uvicorn app.main:app --reload
```

Check:

```bash
curl http://127.0.0.1:8000/health
```

## Tool I/O Examples

### 1) `convert_currency`

Request args:

```json
{"from_currency":"USD","to_currency":"EUR","amount":100}
```

Response shape:

```json
{
  "from_currency":"USD",
  "to_currency":"EUR",
  "amount":100.0,
  "converted":92.5,
  "rate":0.925,
  "rate_date":"2026-03-31",
  "source":"open.er-api.com"
}
```

### 2) `get_crypto_price`

Request args:

```json
{"asset":"bitcoin","vs_currency":"usd"}
```

Response shape:

```json
{
  "asset":"bitcoin",
  "vs_currency":"usd",
  "price":45321.17,
  "source":"coingecko.com"
}
```

### 3) `list_transactions`

Request args:

```json
{"start_date":"2026-03-01","end_date":"2026-03-31","limit":10}
```

Response shape:

```json
{
  "count":10,
  "total_available":20,
  "transactions":[{"id":"tx_1020","date":"2026-03-30","merchant":"Employer Inc","category":"salary","amount":4200.0,"currency":"USD","direction":"credit"}]
}
```

### 4) `get_spending_summary`

Request args:

```json
{"start_date":"2026-03-01","end_date":"2026-03-31"}
```

Response shape:

```json
{
  "period":{"start_date":"2026-03-01","end_date":"2026-03-31"},
  "total_spend":4791.05,
  "transaction_count":18,
  "totals_by_category":{"food":266.12,"rent":1600.0},
  "currency":"USD"
}
```

### 5) `flag_anomalies`

Request args:

```json
{"min_amount":1000}
```

Response shape:

```json
{
  "count":2,
  "baseline":{"median":72.36,"mad":48.68},
  "anomalies":[
    {"id":"tx_1014","date":"2026-03-19","merchant":"Airline Co","category":"travel","amount":1280.0,"currency":"USD","reason":"robust_z_score=16.74"}
  ]
}
```

## Tests

```bash
pytest
```

## V1 Constraints

- Fail-fast behavior for external API errors (no retries/caching in V1).
- Mock transaction data is local and seeded.
- Stock data module is intentionally reserved for later versions.

# EarthOne — ELX

**Earth Liquidity Index** — A macro index representing global liquidity conditions.

## Run locally

```bash
pip install -r requirements.txt
uvicorn app:app --reload
```

## API

| Endpoint | Description |
|---|---|
| `/api/elx` | Current ELX value, regime, bias, drivers, asset calls |
| `/api/elx/history?days=365` | Historical ELX time series |
| `/api/elx/markets` | SPX, Gold, BTC, USD with correlations |

## Stack

FastAPI · Vanilla JS · Custom SVG chart

---

*Data is simulated. Not financial advice.*

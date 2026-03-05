# FOMO Market Data API - PRD

## Original Problem Statement
Клонировать репозиторий, изучить архитектуру и развернуть модуль парсера.
Нужно поднять всю логику exchange (биржевые провайдеры) и первый уровень анализа данных.

## Architecture

### Layer 1: Market Data (Exchange Providers)
- **Binance** - Futures USDT-M (403 geo-restricted)
- **Bybit** - USDT Perpetual (403 geo-restricted)  
- **Coinbase** - Spot USD pairs ✅
- **Hyperliquid** - Perp DEX ✅

### Layer 2: Intel (Crypto Intelligence)
| Source | Role | Status |
|--------|------|--------|
| Dropstab | top100 coins, unlock, funding metadata | ⚠️ SSR limited |
| CoinGecko | **Full market (~15k coins)**, categories | ✅ Working |
| CryptoRank | VC data, funding rounds | Ready (ingest) |

## Data Source Roles (Final Architecture)
```
MARKET DATA (prices)
├ Binance (geo-blocked)
├ Bybit (geo-blocked)
├ Coinbase ✅
└ Hyperliquid ✅

INTEL DATA
├ CoinGecko → FULL MARKET + categories
├ Dropstab → top100 + unlock/vesting (SSR limited)
└ CryptoRank → VC funding (manual ingest)
```

## What's Been Implemented (2026-03-05)

### Exchange API ✅
- 4 providers: Binance, Bybit, Coinbase, Hyperliquid
- Endpoints: providers, instruments, ticker, orderbook, candles, funding, OI
- Working: Coinbase (378 spot), Hyperliquid (229 perp)

### Intel API ✅
- **CoinGecko sync with full pagination** - NEW
- Dropstab SSR scraper (100 coins)
- MongoDB storage for intel data

### New CoinGecko Endpoints
| Endpoint | Function |
|----------|----------|
| POST /api/intel/sync/coingecko | Full sync (all entities) |
| POST /api/intel/sync/coingecko/global | Global market data |
| POST /api/intel/sync/coingecko/categories | 675 categories |
| POST /api/intel/sync/coingecko/trending | Trending coins |
| POST /api/intel/sync/coingecko/top_coins?limit=100 | Top 100 |
| POST /api/intel/sync/coingecko/markets_full?max_pages=60 | ~15k coins |
| GET /api/intel/sync/coingecko/status | Pool status |

## Database Stats
- CoinGecko projects: 350+ (after 2-page test)
- Dropstab projects: 100
- Categories: 675
- Total intel_projects: 450+

## Known Limitations
- Dropstab SSR returns same data on all pages (client-side pagination)
- Binance/Bybit 403/451 (geo-restrictions)
- CoinGecko rate limit: 30 req/min free tier

## Backlog

### P0 (Done)
- [x] Exchange providers (Coinbase, Hyperliquid working)
- [x] CoinGecko markets_full sync with pagination

### P1 (Next)
- [ ] Full market sync cron (daily ~15k coins)
- [ ] Redis realtime pipeline
- [ ] ClickHouse historical storage

### P2 (Future)
- [ ] VPN/proxy for Binance/Bybit
- [ ] Playwright crawler for Dropstab unlocks
- [ ] Frontend dashboard

## Sync Schedule (Recommended)
```
CoinGecko markets_full  → daily (15k coins)
CoinGecko top_coins     → every 10 min (top 100)
CoinGecko categories    → daily
CoinGecko trending      → every 5 min
Dropstab markets        → every 10 min (top 100)
```

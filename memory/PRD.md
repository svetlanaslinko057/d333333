# FOMO Market Data API - PRD

## Original Problem Statement
Клонировать репозиторий, изучить архитектуру и развернуть модуль парсера.
Нужно поднять всю логику exchange (биржевые провайдеры) и первый уровень анализа данных.

## Architecture (Final)

### Layer 1: Market Data (Exchange Providers)
| Provider | Status | Instruments |
|----------|--------|-------------|
| Binance | ❌ 451 geo-blocked | - |
| Bybit | ❌ 403 geo-blocked | - |
| Coinbase | ✅ Working | 378 spot |
| Hyperliquid | ✅ Working | 229 perp |

### Layer 2: Intel (Crypto Intelligence)
| Source | Role | Status |
|--------|------|--------|
| CoinGecko | **Primary** - Full market (~15k), categories, trending | ✅ |
| Dropstab | SSR top100 only (most pages 404 from server) | ⚠️ |
| CryptoRank | VC data, funding (manual ingest or browser discovery) | Ready |

## Data Source Strategy
```
PRICES (realtime)
├ Coinbase ✅ (378 spot pairs)
└ Hyperliquid ✅ (229 perp contracts)

FULL MARKET (15k+ coins)
└ CoinGecko /coins/markets ✅

INTEL DATA
├ CoinGecko categories/trending ✅
├ Dropstab coins top100 ✅ (SSR only)
└ CryptoRank (browser crawler required)
```

## Implemented (2026-03-05)

### Exchange API ✅
- `/api/exchange/providers` - 4 providers
- `/api/exchange/instruments` - 607 instruments
- `/api/exchange/ticker`, `/orderbook`, `/candles`, `/funding`, `/open-interest`

### Intel API ✅
| Endpoint | Status |
|----------|--------|
| POST /api/intel/sync/coingecko/markets_full | ✅ ~15k coins |
| POST /api/intel/sync/coingecko/categories | ✅ 675 categories |
| POST /api/intel/sync/coingecko/trending | ✅ 15 coins |
| POST /api/intel/sync/dropstab/v2 | ⚠️ Limited (SSR only) |
| GET /api/intel/projects | ✅ |

### Dropstab Scraper v2 (Production)
- Dynamic dataset finder
- Retry with exponential backoff
- Snapshot debugging
- **Limitation**: Dropstab returns 404 for most pages from server IP
  - Working: `/investors` (2 items), homepage
  - Blocked: `/vesting`, `/funding-rounds`, etc.

### CryptoRank Discovery System
- Browser-based endpoint discovery (requires Playwright)
- Sync from discovered endpoints
- Manual JSON ingest for funding/investors/unlocks

## Database Stats
- CoinGecko projects: 350+
- Dropstab projects: 100
- Categories: 675
- Total: 450+

## Known Limitations

### Dropstab
- **SSR blocked** for most pages (404 from server)
- **Solution**: Playwright browser crawler or manual data ingest

### Exchange Providers
- Binance/Bybit geo-blocked (451/403)
- **Solution**: VPN/proxy or use Coinbase+Hyperliquid

### CoinGecko
- Rate limit: 30 req/min free tier
- Full sync takes ~25 min (60 pages × 250 coins)

## Backlog

### P0 (Done)
- [x] Exchange providers (Coinbase, Hyperliquid)
- [x] CoinGecko full market sync
- [x] Dropstab v2 scraper (structure-agnostic)

### P1 (Next)
- [ ] Playwright browser crawler for Dropstab
- [ ] CryptoRank discovery run
- [ ] Scheduled syncs (cron)

### P2 (Future)
- [ ] Redis realtime pipeline
- [ ] ClickHouse historical storage
- [ ] Frontend dashboard

## Sync Schedule (Recommended)
```
CoinGecko markets_full  → daily (15k coins)
CoinGecko top_coins     → every 10 min
CoinGecko categories    → daily
CoinGecko trending      → every 5 min
Dropstab markets v1     → every 10 min (top 100)
```

# FOMO Market Data API - PRD

## Original Problem Statement
Клонировать репозиторий, изучить архитектуру и развернуть модуль парсера.
Нужно поднять всю логику exchange (биржевые провайдеры) и первый уровень анализа данных.

## Final Architecture

### Data Sources Roles
```
MARKET DATA (prices, mcap, volume)
├ CoinGecko → PRIMARY (15k coins, categories, trending)
└ Exchanges → realtime prices (Coinbase, Hyperliquid)

ANALYTICS DATA (redundancy from BOTH sources)
├ CryptoRank → fundraising, investors, unlocks, ICO/IDO
└ Dropstab  → fundraising, investors, unlocks, ICO/IDO

Note: CryptoRank + Dropstab collect SAME data types for redundancy
```

### Discovered Dropstab Internal APIs (via Browser)
```
api2.dropstab.com/portfolio/api/markets        → market overview
api2.dropstab.com/portfolio/api/exchange       → exchanges (paginated)
api2.dropstab.com/portfolio/api/marketTotal/*  → BTC dominance, gas
extra-bff.dropstab.com/v1.2/market-data/*      → market summary
```

### Provider Status
| Provider | Status | Data |
|----------|--------|------|
| Coinbase | ✅ | 378 spot |
| Hyperliquid | ✅ | 229 perp |
| Binance | ❌ 451 | geo-blocked |
| Bybit | ❌ 403 | geo-blocked |

## Implemented (2026-03-05)

### Exchange API ✅
- `/api/exchange/providers` - provider list
- `/api/exchange/instruments` - 607 instruments
- `/api/exchange/ticker`, `/orderbook`, `/candles`, `/funding`, `/open-interest`

### Intel API ✅
| Endpoint | Function |
|----------|----------|
| POST /api/intel/sync/coingecko/markets_full | ~15k coins |
| POST /api/intel/sync/coingecko/top_coins | Top 100 |
| POST /api/intel/sync/dropstab/browser | Playwright scraper |
| POST /api/intel/sync/dropstab/browser/{target} | Single target |
| GET /api/intel/admin/health | System health |

### Browser Scraper ✅
- Playwright-based for bot detection bypass
- Captures XHR/fetch JSON responses
- Discovers internal API endpoints
- Proxy support via GLOBAL_PROXY

### Proxy Management ✅
| Endpoint | Function |
|----------|----------|
| GET /api/intel/admin/proxy/status | Current config |
| POST /api/intel/admin/proxy/set | Set proxy |
| POST /api/intel/admin/proxy/clear | Clear proxy |

### Scheduler ✅
| Job | Interval | Status |
|-----|----------|--------|
| coingecko_markets_full | daily | enabled |
| coingecko_top_coins | 10 min | enabled |
| coingecko_trending | 30 min | enabled |
| dropstab_markets | 10 min | enabled |

## Database Stats
```
intel_projects: 350+
intel_categories: 675
intel_funding: 0 (pending browser scrape)
intel_unlocks: 0 (pending)
```

## Key Discovery

Browser scraper revealed Dropstab's internal APIs:
- `api2.dropstab.com` - Main API
- `extra-bff.dropstab.com` - BFF layer

These can potentially be called directly with proper headers!

## Backlog

### P0 (Done)
- [x] Exchange providers
- [x] CoinGecko full market sync
- [x] Scheduler with jobs
- [x] Browser scraper (Playwright)
- [x] Proxy manager

### P1 (Next)
- [ ] Direct API calls to discovered Dropstab endpoints
- [ ] Full page scrape for unlocks/funding
- [ ] CryptoRank browser discovery

### P2 (Future)
- [ ] Data deduplication (merge sources)
- [ ] Redis realtime pipeline
- [ ] Source failover

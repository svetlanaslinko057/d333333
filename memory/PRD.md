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

### Source Priority Table
| Data Type | Primary | Fallback |
|-----------|---------|----------|
| price | Exchange providers | CoinGecko |
| marketcap | CoinGecko | - |
| categories | CoinGecko | - |
| trending | CoinGecko | - |
| fundraising | CryptoRank + Dropstab | both |
| investors | CryptoRank + Dropstab | both |
| unlocks | CryptoRank + Dropstab | both |
| ICO/IDO/IEO | CryptoRank + Dropstab | both |

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
| POST /api/intel/sync/coingecko/markets_full | ~15k coins (1.2s throttle) |
| POST /api/intel/sync/coingecko/top_coins | Top 100 |
| POST /api/intel/sync/coingecko/categories | 675 categories |
| POST /api/intel/sync/coingecko/trending | 15 trending |
| POST /api/intel/sync/dropstab/v2 | Production scraper |
| GET /api/intel/admin/health | System health |

### Scheduler ✅
| Endpoint | Function |
|----------|----------|
| GET /api/intel/scheduler/status | Job status |
| POST /api/intel/scheduler/start | Start scheduler |
| POST /api/intel/scheduler/stop | Stop scheduler |
| POST /api/intel/scheduler/run/{job} | Run job now |

### Scheduled Jobs
| Job | Interval | Status |
|-----|----------|--------|
| coingecko_markets_full | daily | enabled |
| coingecko_top_coins | 10 min | enabled |
| coingecko_trending | 30 min | enabled |
| coingecko_categories | daily | enabled |
| dropstab_markets | 10 min | enabled |
| dropstab_unlocks | 1h | disabled (browser) |
| dropstab_funding | 2h | disabled (browser) |

### Health Monitor
- Source availability tracking
- Last sync times with age
- Database stats
- Error history (24h)

## Database Stats
```
intel_projects: 350+
intel_categories: 675
intel_funding: 0 (pending CryptoRank/Dropstab browser scrape)
intel_unlocks: 0 (pending)
intel_investors: 0 (pending)
```

## Known Limitations

### Dropstab
- SSR pages blocked (404) from server IP
- **Solution**: Playwright browser crawler or manual ingest

### CoinGecko
- Rate limit: ~50 req/min with 1.2s throttle
- Full sync: ~72 seconds (60 pages)

## Backlog

### P0 (Done)
- [x] Exchange providers
- [x] CoinGecko full market sync
- [x] Scheduler with jobs
- [x] Health monitor

### P1 (Next)
- [ ] Playwright browser crawler for Dropstab/CryptoRank
- [ ] Data deduplication (merge CryptoRank + Dropstab events)
- [ ] Source provenance tracking

### P2 (Future)
- [ ] Redis realtime pipeline
- [ ] ClickHouse historical storage
- [ ] Source failover (CryptoCompare)

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
- **Dropstab SSR Scraper** - coins, unlocks, categories, investors
- **CoinGecko API** - markets, categories, trending
- **CryptoRank Ingest** - VC data, funding rounds

## Core Requirements

### Exchange API Endpoints
| Endpoint | Status |
|----------|--------|
| /api/exchange/providers | ✅ |
| /api/exchange/instruments | ✅ |
| /api/exchange/ticker | ✅ |
| /api/exchange/orderbook | ✅ |
| /api/exchange/candles | ✅ |
| /api/exchange/funding | ✅ |
| /api/exchange/open-interest | ✅ |

### Intel API Endpoints
| Endpoint | Status |
|----------|--------|
| /api/intel/health | ✅ |
| /api/intel/sync/dropstab | ✅ |
| /api/intel/projects | ✅ |

## What's Been Implemented (2026-03-05)

### Market Data Module
- 4 exchange providers registered
- Provider registry with capabilities
- Instrument registry (607 instruments, 484 assets)
- Ticker, orderbook, candles, funding, OI endpoints
- Provider health checks

### Intel Module
- Dropstab SSR scraper (100 coins per sync)
- CoinGecko client with load balancing pool
- MongoDB integration for intel data storage

## Known Limitations

### Dropstab Pagination
- **SSR pagination NOT working** - same data on page 1,2,3
- Client-side JavaScript pagination used
- Solution: browser crawler OR CoinGecko for full market

### Geo Restrictions
- Binance: 451 error (geo-blocked)
- Bybit: 403 error (geo-blocked)
- Working providers: Coinbase, Hyperliquid

## Backlog

### P0 (Critical)
- [ ] Add CoinGecko /coins/markets sync endpoint
- [ ] Fix Dropstab full market scraping

### P1 (High)
- [ ] Redis realtime pipeline
- [ ] ClickHouse historical storage
- [ ] WebSocket streaming

### P2 (Medium)
- [ ] Browser crawler for Dropstab
- [ ] VPN/proxy for Binance/Bybit
- [ ] Frontend dashboard

## Next Tasks
1. Implement CoinGecko markets pagination sync
2. Test full market coverage (~15k coins)
3. Schedule periodic syncs (cron)

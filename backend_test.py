#!/usr/bin/env python3
"""
Market Data API Backend Tests
Comprehensive testing for exchange providers and market data endpoints
"""

import requests
import sys
import time
import json
from datetime import datetime
from typing import Dict, List, Optional

class MarketDataAPITester:
    def __init__(self, base_url="https://analytics-engine-12.preview.emergentagent.com"):
        self.base_url = base_url.rstrip('/')
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        self.session = requests.Session()
        self.session.timeout = 30
        
    def log_result(self, test_name: str, success: bool, details: Dict = None):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {test_name}")
        else:
            print(f"❌ {test_name}")
            if details:
                print(f"   Details: {details}")
        
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details or {}
        })

    def make_request(self, method: str, endpoint: str, params: Dict = None, expected_status: int = 200) -> tuple:
        """Make HTTP request and return (success, response_data, status_code)"""
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method.upper() == 'GET':
                response = self.session.get(url, params=params)
            elif method.upper() == 'POST':
                response = self.session.post(url, json=params)
            else:
                return False, {"error": f"Unsupported method: {method}"}, 0
            
            success = response.status_code == expected_status
            
            try:
                data = response.json()
            except:
                data = {"raw_response": response.text}
            
            return success, data, response.status_code
            
        except Exception as e:
            return False, {"error": str(e)}, 0

    def test_health_endpoint(self):
        """Test basic health check"""
        print("\n🏥 Testing Health Endpoints...")
        
        success, data, status = self.make_request('GET', '/api/health')
        self.log_result("Health Check", success, data if not success else None)
        
        if success:
            # Validate response structure
            required_fields = ['ok', 'service', 'version', 'ts', 'layers']
            missing_fields = [f for f in required_fields if f not in data]
            if missing_fields:
                self.log_result("Health Response Structure", False, 
                              {"missing_fields": missing_fields})
            else:
                self.log_result("Health Response Structure", True)

    def test_root_endpoint(self):
        """Test root API endpoint"""
        print("\n📋 Testing Root Endpoint...")
        
        success, data, status = self.make_request('GET', '/api')
        self.log_result("Root API Endpoint", success, data if not success else None)
        
        if success:
            # Validate endpoints structure
            expected_endpoints = ['market', 'assets', 'exchange', 'whales', 'unlocks']
            if 'endpoints' in data:
                available_endpoints = list(data['endpoints'].keys())
                missing = [ep for ep in expected_endpoints if ep not in available_endpoints]
                if missing:
                    self.log_result("Root Endpoints Structure", False, 
                                  {"missing_endpoints": missing})
                else:
                    self.log_result("Root Endpoints Structure", True)

    def test_providers_endpoints(self):
        """Test provider-related endpoints"""
        print("\n🏢 Testing Provider Endpoints...")
        
        # Test providers list
        success, data, status = self.make_request('GET', '/api/exchange/providers')
        self.log_result("Providers List", success, data if not success else None)
        
        providers = []
        if success and 'providers' in data:
            providers = data['providers']
            expected_venues = ['binance', 'bybit', 'coinbase', 'hyperliquid']
            found_venues = [p.get('venue') for p in providers]
            missing_venues = [v for v in expected_venues if v not in found_venues]
            
            if missing_venues:
                self.log_result("All Expected Providers Present", False, 
                              {"missing_venues": missing_venues})
            else:
                self.log_result("All Expected Providers Present", True)
        
        # Test providers health
        success, data, status = self.make_request('GET', '/api/exchange/providers/health')
        self.log_result("Providers Health Check", success, data if not success else None)
        
        working_providers = []
        if success and 'providers' in data:
            for venue, health in data['providers'].items():
                is_healthy = health.get('healthy', False)
                if is_healthy:
                    working_providers.append(venue)
                    print(f"   ✅ {venue}: healthy (latency: {health.get('latency_ms')}ms)")
                else:
                    error = health.get('error', 'Unknown error')
                    print(f"   ❌ {venue}: unhealthy - {error}")
        
        return working_providers

    def test_instruments_endpoints(self, working_providers: List[str]):
        """Test instruments endpoints"""
        print("\n🔧 Testing Instruments Endpoints...")
        
        # Test general instruments endpoint
        success, data, status = self.make_request('GET', '/api/exchange/instruments')
        self.log_result("Instruments - General", success, data if not success else None)
        
        # Test with specific providers and market types
        test_cases = [
            {'venue': 'coinbase', 'market_type': 'spot'},
            {'venue': 'hyperliquid', 'market_type': 'perp'},
        ]
        
        for case in test_cases:
            venue = case['venue']
            if venue not in working_providers:
                print(f"   ⏭️ Skipping {venue} - not healthy")
                continue
                
            params = {'venue': venue, 'market_type': case['market_type']}
            success, data, status = self.make_request('GET', '/api/exchange/instruments', params)
            test_name = f"Instruments - {venue} {case['market_type']}"
            self.log_result(test_name, success, data if not success else None)
            
            if success and 'items' in data:
                instruments_count = len(data['items'])
                print(f"   📊 Found {instruments_count} instruments for {venue} {case['market_type']}")

    def test_ticker_endpoints(self, working_providers: List[str]):
        """Test ticker endpoints"""
        print("\n💰 Testing Ticker Endpoints...")
        
        # Test cases for different providers
        test_cases = [
            {'venue': 'coinbase', 'symbol': 'BTC-USD'},
            {'venue': 'hyperliquid', 'symbol': 'BTC-PERP'},
        ]
        
        for case in test_cases:
            venue = case['venue']
            if venue not in working_providers:
                print(f"   ⏭️ Skipping {venue} - not healthy")
                continue
                
            params = {'venue': venue, 'symbol': case['symbol']}
            success, data, status = self.make_request('GET', '/api/exchange/ticker', params)
            test_name = f"Ticker - {venue} {case['symbol']}"
            self.log_result(test_name, success, data if not success else None)
            
            if success:
                # Validate ticker structure
                required_fields = ['last', 'bid', 'ask', 'volume_24h']
                missing_fields = [f for f in required_fields if f not in data or data[f] is None]
                if missing_fields:
                    self.log_result(f"Ticker Structure - {venue}", False, 
                                  {"missing_fields": missing_fields})
                else:
                    self.log_result(f"Ticker Structure - {venue}", True)
                    print(f"   📈 {venue} {case['symbol']}: ${data.get('last')} (24h vol: ${data.get('volume_24h')})")

    def test_orderbook_endpoints(self, working_providers: List[str]):
        """Test orderbook endpoints"""
        print("\n📚 Testing Orderbook Endpoints...")
        
        test_cases = [
            {'venue': 'hyperliquid', 'symbol': 'BTC-PERP', 'depth': 10},
        ]
        
        for case in test_cases:
            venue = case['venue']
            if venue not in working_providers:
                print(f"   ⏭️ Skipping {venue} - not healthy")
                continue
                
            params = {'venue': venue, 'symbol': case['symbol'], 'depth': case['depth']}
            success, data, status = self.make_request('GET', '/api/exchange/orderbook', params)
            test_name = f"Orderbook - {venue} {case['symbol']}"
            self.log_result(test_name, success, data if not success else None)
            
            if success:
                # Validate orderbook structure
                required_fields = ['bids', 'asks', 'depth']
                missing_fields = [f for f in required_fields if f not in data]
                if missing_fields:
                    self.log_result(f"Orderbook Structure - {venue}", False, 
                                  {"missing_fields": missing_fields})
                else:
                    bids_count = len(data.get('bids', []))
                    asks_count = len(data.get('asks', []))
                    self.log_result(f"Orderbook Structure - {venue}", True)
                    print(f"   📊 {venue} orderbook: {bids_count} bids, {asks_count} asks")

    def test_candles_endpoints(self, working_providers: List[str]):
        """Test candles endpoints"""
        print("\n🕯️ Testing Candles Endpoints...")
        
        test_cases = [
            {'venue': 'coinbase', 'symbol': 'BTC-USD', 'granularity': '1h', 'limit': 5},
        ]
        
        for case in test_cases:
            venue = case['venue']
            if venue not in working_providers:
                print(f"   ⏭️ Skipping {venue} - not healthy")
                continue
                
            params = {
                'venue': venue, 
                'symbol': case['symbol'], 
                'granularity': case['granularity'],
                'limit': case['limit']
            }
            success, data, status = self.make_request('GET', '/api/exchange/candles', params)
            test_name = f"Candles - {venue} {case['symbol']}"
            self.log_result(test_name, success, data if not success else None)
            
            if success and 'candles' in data:
                candles_count = len(data['candles'])
                print(f"   📊 {venue} candles: {candles_count} candles returned")
                
                # Validate candle structure
                if candles_count > 0:
                    candle = data['candles'][0]
                    required_fields = ['t', 'o', 'h', 'l', 'c', 'v']
                    missing_fields = [f for f in required_fields if f not in candle]
                    if missing_fields:
                        self.log_result(f"Candle Structure - {venue}", False, 
                                      {"missing_fields": missing_fields})
                    else:
                        self.log_result(f"Candle Structure - {venue}", True)

    def test_derivatives_endpoints(self, working_providers: List[str]):
        """Test derivatives-specific endpoints"""
        print("\n📈 Testing Derivatives Endpoints...")
        
        # Only test with Hyperliquid as it supports derivatives
        if 'hyperliquid' not in working_providers:
            print("   ⏭️ Skipping derivatives tests - Hyperliquid not healthy")
            return
            
        venue = 'hyperliquid'
        symbol = 'BTC-PERP'
        
        # Test funding rate
        params = {'venue': venue, 'symbol': symbol}
        success, data, status = self.make_request('GET', '/api/exchange/funding', params)
        self.log_result(f"Funding Rate - {venue}", success, data if not success else None)
        
        if success:
            funding_rate = data.get('funding_rate')
            if funding_rate is not None:
                print(f"   📊 {venue} BTC funding rate: {funding_rate}%")
        
        # Test open interest
        success, data, status = self.make_request('GET', '/api/exchange/open-interest', params)
        self.log_result(f"Open Interest - {venue}", success, data if not success else None)
        
        if success:
            oi = data.get('open_interest')
            oi_usd = data.get('open_interest_usd')
            if oi is not None:
                print(f"   📊 {venue} BTC OI: {oi} (${oi_usd})")

    def test_error_handling(self):
        """Test API error handling"""
        print("\n🚫 Testing Error Handling...")
        
        # Test invalid venue
        params = {'venue': 'invalid_venue', 'symbol': 'BTC-USD'}
        success, data, status = self.make_request('GET', '/api/exchange/ticker', params, expected_status=400)
        self.log_result("Invalid Venue Error", success, data if not success else None)
        
        # Test missing parameters
        success, data, status = self.make_request('GET', '/api/exchange/ticker', expected_status=400)
        self.log_result("Missing Parameters Error", success, data if not success else None)
        
        # Test invalid symbol format for instrument_id
        params = {'instrument_id': 'invalid_format'}
        success, data, status = self.make_request('GET', '/api/exchange/ticker', params, expected_status=400)
        self.log_result("Invalid Instrument ID Format", success, data if not success else None)

    def run_all_tests(self):
        """Run all tests"""
        print("🚀 Starting Market Data API Tests...")
        print(f"📡 Testing against: {self.base_url}")
        print("=" * 60)
        
        start_time = time.time()
        
        # Core API tests
        self.test_health_endpoint()
        self.test_root_endpoint()
        
        # Provider tests
        working_providers = self.test_providers_endpoints()
        print(f"\n🔥 Working providers: {working_providers}")
        
        if not working_providers:
            print("⚠️ No working providers found - skipping data tests")
        else:
            # Data endpoints tests
            self.test_instruments_endpoints(working_providers)
            self.test_ticker_endpoints(working_providers)
            self.test_orderbook_endpoints(working_providers)
            self.test_candles_endpoints(working_providers)
            self.test_derivatives_endpoints(working_providers)
        
        # Error handling tests
        self.test_error_handling()
        
        # Summary
        end_time = time.time()
        duration = end_time - start_time
        
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        print(f"Total tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {self.tests_run - self.tests_passed}")
        print(f"Success rate: {(self.tests_passed / self.tests_run * 100):.1f}%")
        print(f"Duration: {duration:.2f} seconds")
        print(f"Working providers: {working_providers}")
        
        return self.tests_passed == self.tests_run

def main():
    """Main test runner"""
    tester = MarketDataAPITester()
    
    try:
        success = tester.run_all_tests()
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n⏹️ Tests interrupted by user")
        return 2
    except Exception as e:
        print(f"\n💥 Test runner crashed: {e}")
        return 3

if __name__ == "__main__":
    sys.exit(main())
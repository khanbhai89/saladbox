"""Cryptocurrency and stock price tool."""

from __future__ import annotations

import aiohttp
import json
from typing import Optional

from saladbox.tools.base import BaseTool


class FinanceTool(BaseTool):
    """Get cryptocurrency and stock prices."""

    @property
    def name(self) -> str:
        return "finance"

    @property
    def description(self) -> str:
        return (
            "Get current cryptocurrency prices (Bitcoin, Ethereum, etc.) and stock information. "
            "Uses free APIs - CoinGecko for crypto. No API key required for basic usage."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["crypto", "crypto_list", "trending", "exchange_rate"],
                    "description": "Type of finance query",
                },
                "symbol": {
                    "type": "string",
                    "description": "Cryptocurrency symbol or ID (e.g., 'bitcoin', 'ethereum', 'btc')",
                },
                "currency": {
                    "type": "string",
                    "description": "Fiat currency for prices (default: 'usd')",
                },
                "from_currency": {
                    "type": "string",
                    "description": "Source currency for exchange rate",
                },
                "to_currency": {
                    "type": "string",
                    "description": "Target currency for exchange rate",
                },
            },
            "required": ["action"],
        }

    COINGECKO_IDS = {
        "btc": "bitcoin",
        "bitcoin": "bitcoin",
        "eth": "ethereum",
        "ethereum": "ethereum",
        "sol": "solana",
        "solana": "solana",
        "ada": "cardano",
        "cardano": "cardano",
        "xrp": "ripple",
        "ripple": "ripple",
        "doge": "dogecoin",
        "dogecoin": "dogecoin",
        "dot": "polkadot",
        "polkadot": "polkadot",
        "matic": "matic-network",
        "avax": "avalanche-2",
        "link": "chainlink",
        "chainlink": "chainlink",
        "ltc": "litecoin",
        "litecoin": "litecoin",
        "uni": "uniswap",
        "uniswap": "uniswap",
        "atom": "cosmos",
        "cosmos": "cosmos",
        "bnb": "binancecoin",
    }

    async def execute(
        self,
        action: str,
        symbol: Optional[str] = None,
        currency: str = "usd",
        from_currency: Optional[str] = None,
        to_currency: Optional[str] = None,
    ) -> str:
        try:
            if action == "crypto":
                if not symbol:
                    return "Error: 'symbol' required for crypto action"
                return await self._get_crypto_price(symbol.lower(), currency.lower())

            elif action == "crypto_list":
                return await self._get_crypto_list(currency.lower())

            elif action == "trending":
                return await self._get_trending()

            elif action == "exchange_rate":
                if not from_currency or not to_currency:
                    return "Error: 'from_currency' and 'to_currency' required for exchange_rate"
                return await self._get_exchange_rate(
                    from_currency.lower(), to_currency.lower()
                )

            else:
                return f"Unknown action: {action}"

        except aiohttp.ClientError as e:
            return f"Network error: {str(e)}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _get_crypto_price(self, symbol: str, currency: str) -> str:
        coin_id = self.COINGECKO_IDS.get(symbol, symbol)

        url = f"https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": coin_id,
            "vs_currencies": currency,
            "include_24hr_change": "true",
            "include_market_cap": "true",
            "include_24hr_vol": "true",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params=params, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 429:
                    return "Error: Rate limited. Please try again in a minute."
                if resp.status != 200:
                    return f"Error: API returned status {resp.status}"
                data = await resp.json()

        if coin_id not in data:
            return f"Cryptocurrency '{symbol}' not found. Try using the full name (e.g., 'bitcoin')."

        coin_data = data[coin_id]
        price = coin_data.get(currency, "N/A")
        change_24h = coin_data.get(f"{currency}_24h_change", 0) or 0
        market_cap = coin_data.get(f"{currency}_market_cap", 0) or 0
        volume = coin_data.get(f"{currency}_24h_vol", 0) or 0

        change_emoji = "📈" if change_24h >= 0 else "📉"

        return (
            f"**{coin_id.upper()}** ({symbol.upper()})\n"
            f"Price: {currency.upper()} {self._format_number(price)}\n"
            f"24h Change: {change_emoji} {change_24h:.2f}%\n"
            f"Market Cap: {currency.upper()} {self._format_number(market_cap, True)}\n"
            f"24h Volume: {currency.upper()} {self._format_number(volume, True)}"
        )

    async def _get_crypto_list(self, currency: str) -> str:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": currency,
            "order": "market_cap_desc",
            "per_page": 15,
            "page": 1,
            "sparkline": "false",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params=params, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 429:
                    return "Error: Rate limited. Please try again in a minute."
                if resp.status != 200:
                    return f"Error: API returned status {resp.status}"
                data = await resp.json()

        result = [f"**Top 15 Cryptocurrencies by Market Cap ({currency.upper()})**\n"]

        for i, coin in enumerate(data, 1):
            name = coin.get("name", "Unknown")
            symbol = coin.get("symbol", "?").upper()
            price = coin.get("current_price", 0)
            change = coin.get("price_change_percentage_24h", 0) or 0
            change_emoji = "↑" if change >= 0 else "↓"

            result.append(
                f"{i:2}. {name} ({symbol}): {currency.upper()} {self._format_number(price)} "
                f"{change_emoji} {abs(change):.1f}%"
            )

        return "\n".join(result)

    async def _get_trending(self) -> str:
        url = "https://api.coingecko.com/api/v3/search/trending"

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 429:
                    return "Error: Rate limited. Please try again in a minute."
                if resp.status != 200:
                    return f"Error: API returned status {resp.status}"
                data = await resp.json()

        coins = data.get("coins", [])

        result = ["**Trending Cryptocurrencies**\n"]

        for i, item in enumerate(coins[:7], 1):
            coin = item.get("item", {})
            name = coin.get("name", "Unknown")
            symbol = coin.get("symbol", "?").upper()
            market_cap_rank = coin.get("market_cap_rank", "N/A")
            result.append(f"{i}. {name} ({symbol}) - Rank #{market_cap_rank}")

        return "\n".join(result)

    async def _get_exchange_rate(self, from_curr: str, to_curr: str) -> str:
        url = f"https://api.coingecko.com/api/v3/exchange_rates"

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    return f"Error: API returned status {resp.status}"
                data = await resp.json()

        rates = data.get("rates", {})

        if from_curr not in rates:
            return f"Currency '{from_curr}' not found"
        if to_curr not in rates:
            return f"Currency '{to_curr}' not found"

        from_rate = rates[from_curr].get("value", 1)
        to_rate = rates[to_curr].get("value", 1)

        from_name = rates[from_curr].get("name", from_curr.upper())
        to_name = rates[to_curr].get("name", to_curr.upper())

        exchange_rate = to_rate / from_rate

        return (
            f"**Exchange Rate**\n"
            f"1 {from_name} ({from_curr.upper()}) = {exchange_rate:.6f} {to_name} ({to_curr.upper()})\n"
            f"1 {to_name} ({to_curr.upper()}) = {1 / exchange_rate:.6f} {from_name} ({from_curr.upper()})"
        )

    def _format_number(self, num: float, abbreviate: bool = False) -> str:
        if num is None:
            return "N/A"

        if abbreviate and num >= 1_000_000_000:
            return f"{num / 1_000_000_000:.2f}B"
        elif abbreviate and num >= 1_000_000:
            return f"{num / 1_000_000:.2f}M"
        elif abbreviate and num >= 1_000:
            return f"{num / 1_000:.2f}K"
        elif num >= 1:
            return f"{num:,.2f}"
        else:
            return f"{num:.6f}"

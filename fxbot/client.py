"""GMOコイン 外国為替FX API クライアント (標準ライブラリのみ)."""
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request

PUBLIC_URL = "https://forex-api.coin.z.com/public"
PRIVATE_URL = "https://forex-api.coin.z.com/private"


class ApiError(RuntimeError):
    pass


class GmoFxClient:
    def __init__(self, api_key: str = "", secret_key: str = "", timeout: float = 10.0):
        self.api_key = api_key
        self.secret_key = secret_key
        self.timeout = timeout

    # ---- HTTP ----
    def _request(self, method: str, base: str, path: str, query=None, body=None, private=False):
        url = f"{base}{path}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = json.dumps(body) if body is not None else ""
        headers = {"Content-Type": "application/json"}
        if private:
            ts = str(int(time.time() * 1000))
            # 署名対象: timestamp + method + path(クエリなし) + body
            text = ts + method + path + data
            sign = hmac.new(self.secret_key.encode(), text.encode(), hashlib.sha256).hexdigest()
            headers.update({"API-KEY": self.api_key, "API-TIMESTAMP": ts, "API-SIGN": sign})
        req = urllib.request.Request(
            url, data=data.encode() if body is not None else None, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                payload = json.loads(res.read().decode())
        except urllib.error.HTTPError as e:
            raise ApiError(f"HTTP {e.code}: {e.read().decode(errors='replace')}") from e
        if payload.get("status") != 0:
            raise ApiError(f"API error: {payload.get('messages')}")
        return payload.get("data")

    # ---- Public ----
    def ticker(self, symbol: str) -> dict:
        for t in self._request("GET", PUBLIC_URL, "/v1/ticker"):
            if t["symbol"] == symbol:
                return {"bid": float(t["bid"]), "ask": float(t["ask"]), "status": t["status"]}
        raise ApiError(f"ticker not found: {symbol}")

    def symbol_rule(self, symbol: str) -> dict:
        for r in self._request("GET", PUBLIC_URL, "/v1/symbols"):
            if r["symbol"] == symbol:
                return r
        raise ApiError(f"symbol not found: {symbol}")

    # ---- Private ----
    def open_positions(self, symbol: str) -> list:
        data = self._request("GET", PRIVATE_URL, "/v1/openPositions", {"symbol": symbol}, private=True)
        return (data or {}).get("list", [])

    def market_order(self, symbol: str, side: str, size: int) -> list:
        body = {"symbol": symbol, "side": side, "size": str(size), "executionType": "MARKET"}
        return self._request("POST", PRIVATE_URL, "/v1/order", body=body, private=True)

    def close_position(self, symbol: str, position: dict) -> list:
        close_side = "SELL" if position["side"] == "BUY" else "BUY"
        body = {
            "symbol": symbol,
            "side": close_side,
            "executionType": "MARKET",
            "settlePosition": [{"positionId": position["positionId"], "size": str(position["size"])}],
        }
        return self._request("POST", PRIVATE_URL, "/v1/closeOrder", body=body, private=True)

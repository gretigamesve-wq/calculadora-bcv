#!/usr/bin/env python3
"""Fetch current BCV and Binance P2P VES rates and write rates.json.
Falls back to the previous value for any field that can't be fetched reliably."""

import json
import statistics
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RATES_PATH = REPO_ROOT / "rates.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (calculadora-bcv update script)"}


def http_get_json(url, timeout=15):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_post_json(url, payload, timeout=15):
    data = json.dumps(payload).encode("utf-8")
    headers = dict(HEADERS)
    headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_bcv_usd():
    data = http_get_json("https://ve.dolarapi.com/v1/dolares/oficial")
    value = data.get("promedio")
    if not value or value <= 0:
        raise ValueError("bcv usd promedio inválido")
    return round(float(value), 2)


def fetch_bcv_eur():
    data = http_get_json("https://ve.dolarapi.com/v1/euros")
    for row in data:
        if row.get("fuente") == "oficial":
            value = row.get("promedio")
            if not value or value <= 0:
                raise ValueError("bcv eur promedio inválido")
            return round(float(value), 2)
    raise ValueError("no se encontró fuente oficial de EUR")


def fetch_binance_usdt():
    payload = {
        "asset": "USDT",
        "fiat": "VES",
        "tradeType": "SELL",
        "page": 1,
        "rows": 10,
        "payTypes": [],
        "publisherType": None,
    }
    data = http_post_json("https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search", payload)
    ads = data.get("data", [])
    prices = [float(ad["adv"]["price"]) for ad in ads if ad.get("adv", {}).get("price")]
    if len(prices) < 3:
        raise ValueError("muy pocas ofertas de Binance P2P")
    prices.sort()
    top = prices[: max(5, len(prices) // 2)]
    return round(statistics.median(top), 2)


def load_previous():
    if RATES_PATH.exists():
        try:
            return json.loads(RATES_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"bcvUsd": 0, "bcvEur": 0, "binance": 0, "updatedAt": None}


def main():
    previous = load_previous()
    result = dict(previous)
    errors = []

    for key, fetcher in (
        ("bcvUsd", fetch_bcv_usd),
        ("bcvEur", fetch_bcv_eur),
        ("binance", fetch_binance_usdt),
    ):
        try:
            result[key] = fetcher()
        except Exception as exc:  # noqa: BLE001 - log and keep previous value
            errors.append(f"{key}: {exc}")

    result["updatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    RATES_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("rates.json actualizado:", json.dumps(result, ensure_ascii=False))
    if errors:
        print("Avisos (se mantuvo el valor anterior en esos campos):", file=sys.stderr)
        for e in errors:
            print(" -", e, file=sys.stderr)


if __name__ == "__main__":
    main()

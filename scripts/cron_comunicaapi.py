#!/usr/bin/env python3
"""Cron job: busca intimações via ComunicaAPI para múltiplos advogados.

Configurar no .env da VPS:
  COMUNICAAPI_OABS=123456/MG,789012/MG,345678/SP

Formato: numero/UF separados por vírgula.
Cada OAB é consultada individualmente (API aceita 1 por chamada).

Crontab:
  0 9 * * * docker exec casehub-lite python3 /app/scripts/cron_comunicaapi.py >> /var/log/comunicaapi-cron.log 2>&1
"""
import asyncio
import hashlib
import httpx
import os
import sys
from datetime import date, timedelta

BASE_URL = os.environ.get("CASEHUB_BASE_URL", "http://localhost:8001")
PREFIX = os.environ.get("CASEHUB_PREFIX", "/casehub")
ADMIN_EMAIL = os.environ.get("CASEHUB_ADMIN_EMAIL", "victor@vingren.me")
ADMIN_PASSWORD = os.environ.get("CASEHUB_ADMIN_PASSWORD", "")

# Multiple OABs: "123456/MG,789012/MG,345678/SP"
OABS_RAW = os.environ.get("COMUNICAAPI_OABS", "")


def parse_oabs(raw: str) -> list:
    """Parse 'numero/UF,numero/UF' into list of (numero, uf) tuples."""
    result = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if "/" in entry:
            numero, uf = entry.split("/", 1)
            result.append((numero.strip(), uf.strip().upper()))
        else:
            # Assume MG if no UF specified
            result.append((entry.strip(), "MG"))
    return result


async def main():
    oabs = parse_oabs(OABS_RAW)

    if not oabs:
        print("[CRON] COMUNICAAPI_OABS not set. Skipping.")
        print("[CRON] Set in .env: COMUNICAAPI_OABS=123456/MG,789012/MG")
        sys.exit(0)
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        print("[CRON] CASEHUB_ADMIN_EMAIL/CASEHUB_ADMIN_PASSWORD must be set explicitly. Skipping.")
        sys.exit(1)

    hoje = date.today()
    data_inicio = (hoje - timedelta(days=7)).isoformat()
    data_fim = hoje.isoformat()

    print(f"[CRON] {hoje} — {len(oabs)} OAB(s) para consultar, período {data_inicio} a {data_fim}")

    async with httpx.AsyncClient(base_url=BASE_URL, follow_redirects=True, timeout=60) as client:
        # Login
        r = await client.post(f"{PREFIX}/login", data={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
        })
        if r.status_code != 200:
            print(f"[CRON] Login failed: {r.status_code}")
            sys.exit(1)

        total_geral = 0

        for numero, uf in oabs:
            oab_hash = hashlib.sha256(f"{numero}/{uf}".encode("utf-8")).hexdigest()[:10]
            print(f"\n[CRON] Consultando OAB hash={oab_hash}/{uf}...")

            r2 = await client.post(f"{PREFIX}/controladoria/buscar-comunicaapi", json={
                "numero_oab": numero,
                "uf_oab": uf,
                "data_inicio": data_inicio,
                "data_fim": data_fim,
            })

            if r2.status_code == 200:
                data = r2.json()
                if data.get("success") is False or data.get("error"):
                    print(f"[CRON] OAB {uf}: FALHA INTEGRACAO {data.get('code', 'unknown')}")
                    continue
                total = data.get("total", 0)
                total_geral += total
                print(f"[CRON] OAB {uf}: {total} intimação(ões)")
            else:
                try:
                    data = r2.json()
                    code = data.get("code") or f"http_{r2.status_code}"
                except Exception:
                    code = f"http_{r2.status_code}"
                print(f"[CRON] OAB {uf}: FALHA INTEGRACAO {code}")

        print(f"\n[CRON] Total: {total_geral} intimação(ões) para {len(oabs)} advogado(s)")


if __name__ == "__main__":
    asyncio.run(main())

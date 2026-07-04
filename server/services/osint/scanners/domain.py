"""
server/services/osint/scanners/domain.py
=========================================
Domain / IP address OSINT scanner.

Tools used:
  - Google DNS-over-HTTPS (A, MX, TXT, NS records)
  - ip-api.com for IP geolocation (free, no key)
  - WHOIS via whois.iana.org (HTTP fallback)
  - Google Dork query generation

Exports:
    scan_domain(code, target) -> None
    fetch_dns(domain)         -> dict
    fetch_ip_geo(ip)          -> dict
"""

print("[ECHOMARK][scanners/domain.py] Module loaded — Domain/IP scanner initializing")

import re
import requests
from server.storage.cases import upsert_section
from server.services.osint.scanners.shared import _log


def fetch_dns(domain: str) -> dict:
    """
    Query Google DNS-over-HTTPS for A, MX, TXT, NS records.
    Returns dict with record lists.
    """
    clean = re.sub(r"https?://", "", domain).split("/")[0]
    print(f"[ECHOMARK][scanners/domain.py] fetch_dns: querying '{clean}'")
    try:
        def _dns(name, rtype):
            r = requests.get(
                f"https://dns.google/resolve?name={name}&type={rtype}",
                timeout=8
            ).json()
            return [a["data"] for a in r.get("Answer", [])]

        result = {
            "domain":      clean,
            "a_records":   _dns(clean, "A"),
            "mx_records":  _dns(clean, "MX"),
            "txt_records": _dns(clean, "TXT"),
            "ns_records":  _dns(clean, "NS"),
            "cname":       _dns(clean, "CNAME"),
        }
        print(f"[ECHOMARK][scanners/domain.py] fetch_dns: A={result['a_records']}")
        return result
    except Exception as e:
        print(f"[ECHOMARK][scanners/domain.py] fetch_dns: error — {e}")
        return {"domain": clean, "error": str(e)}


def fetch_ip_geo(ip: str) -> dict:
    """
    Query ip-api.com for geolocation of an IP address (free, no key).
    Returns dict or {"error": "..."} on failure.
    """
    print(f"[ECHOMARK][scanners/domain.py] fetch_ip_geo: querying '{ip}'")
    try:
        resp = requests.get(
            f"http://ip-api.com/json/{ip}?fields=status,message,country,regionName,city,zip,lat,lon,isp,org,as,query",
            timeout=8
        )
        resp.raise_for_status()
        raw = resp.json()
        if raw.get("status") != "success":
            return {"error": raw.get("message", "Lookup failed")}
        data = {
            "ip":          raw.get("query", ip),
            "country":     raw.get("country", ""),
            "region":      raw.get("regionName", ""),
            "city":        raw.get("city", ""),
            "zip":         raw.get("zip", ""),
            "lat":         raw.get("lat", 0),
            "lon":         raw.get("lon", 0),
            "isp":         raw.get("isp", ""),
            "org":         raw.get("org", ""),
            "as":          raw.get("as", ""),
        }
        print(f"[ECHOMARK][scanners/domain.py] fetch_ip_geo: {data['city']}, {data['country']} — ISP={data['isp']}")
        return data
    except Exception as e:
        print(f"[ECHOMARK][scanners/domain.py] fetch_ip_geo: error — {e}")
        return {"error": str(e)}


def scan_domain(code: str, target: str) -> None:
    """
    Full domain/IP OSINT pipeline.
    Writes sections: basic, dns, dorking.
    If A records found, also writes IP geolocation.
    """
    print(f"[ECHOMARK][scanners/domain.py] scan_domain: START code={code} target='{target}'")
    _log(code, f"[DOMAIN] Scan started for '{target}'")

    clean = re.sub(r"https?://", "", target).split("/")[0]
    is_ip = bool(re.match(r"^\d{1,3}(\.\d{1,3}){3}$", clean))

    # --- Basic ---
    upsert_section(code, "basic", {
        "section": "basic",
        "query":   target,
        "type":    "ip" if is_ip else "domain",
        "clean":   clean,
        "notes":   f"{'IP address' if is_ip else 'Domain'} target — running DNS and geolocation lookup."
    })
    _log(code, f"[DOMAIN] Basic section written — is_ip={is_ip}")

    if is_ip:
        # --- IP geolocation directly ---
        geo = fetch_ip_geo(clean)
        upsert_section(code, "dns", {
            "section":     "dns",
            "query":       target,
            "ip":          clean,
            "geolocation": geo
        })
        _log(code, f"[DOMAIN] IP geo: {geo.get('city')}, {geo.get('country')}")
    else:
        # --- DNS records ---
        dns = fetch_dns(clean)
        geo_data = {}
        if dns.get("a_records"):
            geo_data = fetch_ip_geo(dns["a_records"][0])
            _log(code, f"[DOMAIN] IP geo for first A record: {geo_data.get('city')}, {geo_data.get('country')}")

        upsert_section(code, "dns", {
            "section":     "dns",
            "query":       target,
            "geolocation": geo_data,
            **dns
        })
        _log(code, f"[DOMAIN] DNS section written — A={dns.get('a_records', [])}")

    # --- Dorking queries ---
    upsert_section(code, "dorking", {
        "section": "dorking",
        "queries": [
            f'site:{clean}',
            f'"{clean}" filetype:pdf',
            f'"{clean}" inurl:admin OR inurl:login OR inurl:dashboard',
            f'"{clean}" intitle:"index of"',
            f'"{clean}" intext:password OR intext:passwd',
            f'"{clean}" ext:xml OR ext:conf OR ext:cnf OR ext:reg OR ext:inf',
            f'"{clean}" ext:sql OR ext:dbf OR ext:mdb',
        ],
        "note": "Run these queries manually in Google / Bing / DuckDuckGo."
    })
    _log(code, "[DOMAIN] Dorking queries generated")

    _log(code, "[DOMAIN] All sections written")
    print(f"[ECHOMARK][scanners/domain.py] scan_domain: END code={code}")


print("[ECHOMARK][scanners/domain.py] Module ready — fetch_dns, fetch_ip_geo, scan_domain exported")

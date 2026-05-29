#!/usr/bin/env python3
"""Import an Openbank roboadvisor portfolioTracking API response into the
portfolio tracker as balance_entries.

Usage:
    python scripts/import_openbank.py response.json --asset-id 61
    python scripts/import_openbank.py response.json --asset-id 61 --dry-run
    python scripts/import_openbank.py response.json --asset-id 61 --import-deposits
    python scripts/import_openbank.py response.json --asset-id 61 --reset-valuations

Default behaviour (upsert):
    Inserts each valuation for its date. If a snapshot already exists for that
    date it is overwritten. Snapshots for dates NOT present in the JSON are left
    untouched — useful for incremental daily updates.

With --reset-valuations:
    Deletes ALL existing snapshots (and deposits/withdrawals when combined with
    --import-deposits) for the asset before importing. Use when you want a clean
    slate, e.g. after correcting historical data.

Deposit detection:
    The Openbank API returns a timeWeightedReturn (TWR) that measures investment
    performance excluding cash flows. When the portfolio value jumps more than
    the TWR implies, the difference is a deposit (or withdrawal if negative).
    Formula: deposit = valuation[t] - valuation[t-1] * (1 + twr[t]) / (1 + twr[t-1])
"""
import argparse
import json
import sys

try:
    import requests
except ImportError:
    sys.exit("pip install requests")


def _val(entry: dict) -> float:
    v = entry["valuation"]
    return float(v["parsedValue"] if isinstance(v, dict) else v)


def _twr(entry: dict) -> float:
    t = entry["timeWeightedReturn"]
    return float(t["parsedValue"] if isinstance(t, dict) else t)


def extract_snapshots(entries: list) -> list:
    return [{"date": e["bookingDate"], "amount_eur": round(_val(e), 2), "type": "snapshot"} for e in entries]


def detect_deposits(entries: list, threshold: float = 200.0) -> list:
    """Return detected cash flows (deposits > threshold, withdrawals < -threshold).

    The first entry is always the initial deposit — its full valuation is the amount.
    """
    deposits = []

    # Day 0: initial investment
    first = entries[0]
    if _val(first) > threshold:
        deposits.append({
            "date": first["bookingDate"],
            "amount_eur": round(_val(first), 2),
            "type": "deposit",
        })

    for i in range(1, len(entries)):
        prev, curr = entries[i - 1], entries[i]
        prev_twr, curr_twr = _twr(prev), _twr(curr)
        prev_val, curr_val = _val(prev), _val(curr)

        # Chain the TWR to get the market-only return for this period
        market_return = (1 + curr_twr) / (1 + prev_twr) - 1
        expected = prev_val * (1 + market_return)
        flow = curr_val - expected

        if flow > threshold:
            deposits.append({"date": curr["bookingDate"], "amount_eur": round(flow, 2), "type": "deposit"})
        elif flow < -threshold:
            deposits.append({"date": curr["bookingDate"], "amount_eur": round(abs(flow), 2), "type": "withdrawal"})

    return deposits


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", help="Openbank JSON response file")
    ap.add_argument("--asset-id", type=int, required=True, help="Balance asset ID in portfolio tracker")
    ap.add_argument("--base-url", default="http://localhost:3001", help="Portfolio tracker API base URL")
    ap.add_argument("--deposit-threshold", type=float, default=200.0,
                    help="Min EUR delta to count as a cash flow (default: 200)")
    ap.add_argument("--dry-run", action="store_true", help="Print plan without posting to API")
    ap.add_argument("--import-deposits", action="store_true",
                    help="Also import detected deposits (skipped by default; use if starting fresh)")
    ap.add_argument("--reset-valuations", action="store_true",
                    help="Delete ALL existing snapshots (and deposits when --import-deposits is set) "
                         "before importing. Default upserts per date, leaving other dates untouched.")
    args = ap.parse_args()

    with open(args.file, encoding="utf-8") as f:
        data = json.load(f)

    entries = data["valuations"]
    print(f"Loaded {len(entries)} entries  ({entries[0]['bookingDate']} to {entries[-1]['bookingDate']})")

    snapshots = extract_snapshots(entries)
    deposits = detect_deposits(entries, threshold=args.deposit_threshold)

    print(f"\n-- Detected cash flows ------------------------------------------")
    for d in deposits:
        tag = "+" if d["type"] == "deposit" else "-"
        print(f"  {d['date']}  {tag}{d['amount_eur']:>10,.2f} EUR  ({d['type']})")
    total_dep = sum(d["amount_eur"] for d in deposits if d["type"] == "deposit")
    print(f"  Total deposits detected: {total_dep:,.2f} EUR")

    print(f"\n-- Snapshots ----------------------------------------------------")
    print(f"  {len(snapshots)} daily valuations")
    print(f"  First: {snapshots[0]['date']}  {snapshots[0]['amount_eur']:>10,.2f} EUR")
    print(f"  Last:  {snapshots[-1]['date']}  {snapshots[-1]['amount_eur']:>10,.2f} EUR")

    if args.dry_run:
        print("\n[DRY RUN] Nothing posted. Remove --dry-run to import.")
        return

    base = args.base_url.rstrip("/")
    replace_param = "true" if args.reset_valuations else "false"

    mode_label = "RESET (wipe + reinsert)" if args.reset_valuations else "UPSERT (overwrite per date)"
    print(f"\nImport mode: {mode_label}")

    print(f"\nPosting {len(snapshots)} snapshots to asset {args.asset_id}...")
    r = requests.post(f"{base}/api/balance/{args.asset_id}/import?replace={replace_param}", json=snapshots, timeout=30)
    r.raise_for_status()
    res = r.json()
    print(f"  OK inserted={res['inserted']}  errors={len(res['errors'])}")
    for e in res["errors"][:5]:
        print(f"    ERR {e}")

    if args.import_deposits:
        print(f"\nPosting {len(deposits)} detected deposits...")
        r = requests.post(f"{base}/api/balance/{args.asset_id}/import?replace={replace_param}", json=deposits, timeout=30)
        r.raise_for_status()
        res = r.json()
        print(f"  OK inserted={res['inserted']}  errors={len(res['errors'])}")
        for e in res["errors"][:5]:
            print(f"    ERR {e}")
    else:
        print("\n[Deposits skipped -- your manually entered ones are preserved]")
        print("  Pass --import-deposits to override with auto-detected amounts.")

    print("\nDone.")


if __name__ == "__main__":
    main()

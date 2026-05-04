"""
Generate the Banregio Reconciliation Report v2 .xlsx for a given run.

Usage:
    cd Backend
    python -m scripts.generate_banregio_report --process-id 5
    python -m scripts.generate_banregio_report --process-id 5 --output /tmp/x.xlsx
    python -m scripts.generate_banregio_report --process-id 5 --opening-balance 1234.56

Default output:
    docs/audits/RECONCILIACION_BANREGIO_{MES}_{AÑO}_v2.xlsx
    (relative to the repo root, alongside the audit reports)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models.process import AccountingProcess
from app.services.banregio_report_v2 import builder


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Banregio Reconciliation Report v2")
    parser.add_argument("--process-id", type=int, required=True)
    parser.add_argument("--output", default=None,
                        help="Output xlsx path. Default: docs/audits/{filename}.xlsx")
    parser.add_argument("--opening-balance", type=float, default=0.0,
                        help="SALDO INICIAL — default 0.00")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        process = db.query(AccountingProcess).filter_by(id=args.process_id).first()
        if not process:
            print(f"❌ process_id={args.process_id} not found")
            return 1

        # Resolve output path
        if args.output:
            output = Path(args.output)
        else:
            output = (
                Path(__file__).resolve().parent.parent.parent
                / "docs" / "audits"
                / builder.default_filename(process)
            )

        print(f"Building 3-sheet workbook for process_id={process.id} ({process.name})…")
        stats = builder.build_to_path(
            db, process, output, opening_balance=args.opening_balance
        )

        print()
        print("=== Sheet 1 stats ===")
        for k, v in stats["sheet1"].items():
            if isinstance(v, float):
                print(f"  {k:25s} ${v:,.2f}")
            else:
                print(f"  {k:25s} {v}")

        print()
        print("=== Sheet 2 — Resumen Consolidado ===")
        for k, v in stats["sheet2"]["resumen"].items():
            print(f"  {k:25s} ${v:,.2f}")

        print()
        print("=== Sheet 3 — Alertas ===")
        print(f"  pending_count             {stats['sheet3']['pending_count']}")
        print(f"  alert_count               {stats['sheet3']['alert_count']}")
        for level, n in stats["sheet3"]["alerts_by_level"].items():
            if n:
                print(f"    {level:10s} {n}")

        print()
        print(f"✅ Report written to: {output}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

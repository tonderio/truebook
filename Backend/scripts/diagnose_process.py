"""
Diagnostic CLI — dump everything about a process so FinOps / IT can
triage "report shows 0%, why?" without a Python REPL.

Usage:
    cd Backend
    python -m scripts.diagnose_process --process-id 5
    python -m scripts.diagnose_process --process-id 5 --logs 100

Read-only. Safe to run on any environment (local, prod) — the only
side effect is printing.

What it shows:
  1. AccountingProcess fields (status, stage, coverage, timestamps)
  2. UploadedFile rows + statuses
  3. Per-result-table presence (KushkiResult, BanregioResult, etc.)
  4. Classification distribution (counts per category)
  5. Adjustments + alerts summary
  6. Last N ProcessLog entries (50 by default)
  7. Diagnostic verdict — best guess at what's wrong if anything
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models.process import AccountingProcess, ProcessLog
from app.models.file import UploadedFile
from app.models.result import (
    KushkiResult, BanregioResult, FeesResult, ConciliationResult,
)
from app.models.bitso import BitsoReport, BitsoReportLine
from app.models.classification import BanregioMovementClassification
from app.models.adjustment import RunAdjustment
from app.models.alert import RunAlert


def fmt_bool(v: bool) -> str:
    return "✅" if v else "❌"


def fmt_money(v) -> str:
    if v is None:
        return "—"
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return str(v)


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose a TrueBook process")
    parser.add_argument("--process-id", type=int, required=True)
    parser.add_argument("--logs", type=int, default=50,
                        help="Max ProcessLog entries to show (default 50)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        proc = db.query(AccountingProcess).filter_by(id=args.process_id).first()
        if not proc:
            print(f"❌ process_id={args.process_id} not found")
            return 1

        # ── 1. Process header ──────────────────────────────────────────
        print("=" * 78)
        print(f"PROCESS DIAGNOSTIC — process_id={proc.id}")
        print("=" * 78)
        print(f"  name              {proc.name}")
        print(f"  period            {proc.period_year}-{str(proc.period_month).zfill(2)}")
        print(f"  status            {proc.status}")
        print(f"  current_stage     {proc.current_stage}")
        print(f"  progress          {proc.progress}%")
        print(f"  coverage_pct      {proc.coverage_pct}")
        print(f"  bank_account      {proc.bank_account}")
        print(f"  acquirers         {proc.acquirers}")
        print(f"  created_at        {proc.created_at}")
        print(f"  reconciled_at     {getattr(proc, 'reconciled_at', None)}")
        print(f"  error_message     {getattr(proc, 'error_message', None)}")
        print()

        # ── 2. Files ───────────────────────────────────────────────────
        files = db.query(UploadedFile).filter_by(process_id=proc.id).all()
        print(f"FILES ({len(files)}):")
        if not files:
            print("  (none)")
        else:
            print(f"  {'id':<5} {'type':<10} {'status':<10} {'size':<10} {'name'}")
            for f in files:
                size = f"{f.file_size / 1024:.1f} KB" if f.file_size else "—"
                print(f"  {f.id:<5} {f.file_type:<10} {f.status:<10} {size:<10} {f.original_name}")
        print()

        # ── 3. Result tables ───────────────────────────────────────────
        kr = db.query(KushkiResult).filter_by(process_id=proc.id).first()
        br = db.query(BanregioResult).filter_by(process_id=proc.id).first()
        fr = db.query(FeesResult).filter_by(process_id=proc.id).first()
        bitso_rpt = db.query(BitsoReport).filter_by(process_id=proc.id).first()
        bitso_lines = (
            db.query(BitsoReportLine).filter_by(report_id=bitso_rpt.id).count()
            if bitso_rpt else 0
        )
        cr_rows = db.query(ConciliationResult).filter_by(process_id=proc.id).all()
        cls_count = (
            db.query(BanregioMovementClassification).filter_by(process_id=proc.id).count()
        )
        cls_unclassified = (
            db.query(BanregioMovementClassification)
            .filter(
                BanregioMovementClassification.process_id == proc.id,
                BanregioMovementClassification.classification == "unclassified",
            )
            .count()
        )
        adj_count = db.query(RunAdjustment).filter_by(process_id=proc.id).count()
        alert_count = db.query(RunAlert).filter_by(process_id=proc.id).count()

        print("RESULT TABLES:")
        print(f"  {fmt_bool(kr is not None)} KushkiResult           "
              f"total_net_deposit={fmt_money(kr.total_net_deposit) if kr else '—'}, "
              f"daily_summary_rows={len(kr.daily_summary or []) if kr else 0}")
        print(f"  {fmt_bool(br is not None)} BanregioResult         "
              f"movements={len(br.movements or []) if br else 0}")
        print(f"  {fmt_bool(fr is not None)} FeesResult             "
              f"total_fees={fmt_money(fr.total_fees) if fr else '—'}")
        print(f"  {fmt_bool(bitso_rpt is not None)} BitsoReport            "
              f"lines={bitso_lines}, total={fmt_money(bitso_rpt.total_amount) if bitso_rpt else '—'}")
        print(f"  {fmt_bool(len(cr_rows) > 0)} ConciliationResult     {len(cr_rows)} rows")
        for cr in cr_rows:
            td = float(cr.total_difference or 0)
            print(f"      - {cr.conciliation_type:25s}  total_diff={fmt_money(td)}")
        print(f"  {fmt_bool(cls_count > 0)} BanregioMovementClassification  "
              f"{cls_count} rows ({cls_unclassified} unclassified)")
        print(f"  {fmt_bool(adj_count > 0)} RunAdjustment           {adj_count} rows")
        print(f"  {fmt_bool(alert_count > 0)} RunAlert                {alert_count} rows")
        print()

        # ── 4. Classification distribution ─────────────────────────────
        if cls_count > 0:
            from sqlalchemy import func
            dist = (
                db.query(
                    BanregioMovementClassification.classification,
                    func.count(BanregioMovementClassification.id),
                )
                .filter_by(process_id=proc.id)
                .group_by(BanregioMovementClassification.classification)
                .all()
            )
            print(f"CLASSIFICATION DISTRIBUTION:")
            for cat, n in sorted(dist, key=lambda x: -x[1]):
                print(f"  {n:5d}  {cat}")
            print()

        # ── 5. Recent ProcessLog rows ──────────────────────────────────
        logs = (
            db.query(ProcessLog)
            .filter_by(process_id=proc.id)
            .order_by(ProcessLog.created_at.desc(), ProcessLog.id.desc())
            .limit(args.logs)
            .all()
        )
        print(f"RECENT PROCESS LOGS (last {len(logs)} of max {args.logs}):")
        if not logs:
            print("  (none)")
        else:
            for log in reversed(logs):  # oldest-first for readable narrative
                ts = log.created_at.strftime("%Y-%m-%d %H:%M:%S") if log.created_at else "—"
                level = log.level or "info"
                level_marker = {"info": "·", "warning": "⚠", "error": "❌"}.get(level, "·")
                print(f"  {ts}  {level_marker} [{log.stage:20s}] {log.message[:120]}")
        print()

        # ── 6. Verdict ─────────────────────────────────────────────────
        print("VERDICT:")
        verdicts: list[str] = []

        if not files:
            verdicts.append("• No files uploaded — pipeline cannot run. Upload Kushki + Banregio files first.")
        if br is None:
            verdicts.append("• BanregioResult missing — Stage 6 (parsing) didn't write. Either no Banregio file uploaded or all parses failed.")
        elif not (br.movements or []):
            verdicts.append("• BanregioResult exists but movements is empty — Stage 6 ran but every Banregio file failed to parse. Check 'Error en parseando' log entries.")
        elif cls_count == 0:
            stage8_logs = [l for l in logs if "clasif" in (l.message or "").lower() or l.stage == "classification"]
            if any("error" in (l.level or "").lower() for l in stage8_logs):
                verdicts.append("• Stage 8 raised an exception (see ProcessLog 'classification' entries with level=error). Pre-Step-2 builds logged this as 'warning' so it may show as ⚠ above.")
            elif any("clasificación completada" in (l.message or "").lower() for l in stage8_logs):
                verdicts.append("• Stage 8 logged success but BanregioMovementClassification is empty — possible DB rollback or rows deleted by another process.")
            elif not stage8_logs:
                verdicts.append("• Stage 8 never started — pipeline likely never ran (status set manually?) OR the run was interrupted before Stage 8.")
            else:
                verdicts.append("• Stage 8 ran but didn't produce classifications. Check the 'classification' stage logs above.")
        elif cls_unclassified == cls_count:
            verdicts.append("• Stage 8 ran but classified everything as 'unclassified'. Either the classifier rules don't match this period's Banregio description format, or the input movements are malformed.")
        elif cls_unclassified > 0:
            pct = cls_unclassified / cls_count * 100
            verdicts.append(f"• {cls_unclassified}/{cls_count} ({pct:.1f}%) movements still unclassified — consider extending classifier rules.")

        if proc.status == "completed" and (proc.coverage_pct or 0) < 100:
            verdicts.append(f"• status='completed' but coverage={proc.coverage_pct}% — process completed with gaps. The v2 report endpoint will refuse to generate (after Step 2 lands).")

        if not verdicts:
            verdicts.append("✅ No issues detected — everything looks healthy.")

        for v in verdicts:
            print(f"  {v}")
        print()

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

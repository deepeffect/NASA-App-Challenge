"""reports/metrics.json'u kısa bir tablo olarak yazdırır: python show_metrics.py"""
import json
from pathlib import Path

r = json.loads((Path(__file__).parent / "reports" / "metrics.json").read_text(encoding="utf-8"))
print("satırlar:", r["rows"], "| veri artırma:", r.get("augmentation"))
for split in ("val", "val_real_only", "test", "control"):
    if split not in r:
        continue
    print(f"\n== {split}")
    for name, v in r[split].items():
        o = v["onset"]
        line = (f"  {name:32s} MAE {v['mae_z']:.3f} | kötü hedefte MAE {v['mae_z_when_target_yellow_or_red']} | "
                f"yeni sorun: {o['true_new_problems']}, yakalanan {o['hit']}, yanlış alarm {o['false_alarm']}, "
                f"kesinlik {o['precision']}, duyarlılık {o['recall']}")
        if "onset_possible_p90" in v:
            q = v["onset_possible_p90"]
            line += f" || p90 'olası': yakalanan {q['hit']}, yanlış alarm {q['false_alarm']}, kesinlik {q['precision']}, duyarlılık {q['recall']}"
        if "interval_80_coverage" in v:
            line += f" | %80 aralık kapsaması {v['interval_80_coverage']}"
        print(line)
for k in ("test_lead_times", "test_lead_times_possible_p90", "test_flags_possible_p90",
          "control_false_alarms_by_indicator", "control_false_alarms_possible_p90"):
    if k in r:
        print(f"\n{k}:")
        for row in r[k]:
            print("  ", row)

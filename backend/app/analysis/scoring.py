"""Sağlık sistemi başına 0-100 skor ve genel durum (green/yellow/red/unknown).

skor = 100 − Σ (sistemdeki her metrik için o metriği içeren aktif olayların EN YÜKSEK cezası)
  - Aynı metrik için hem eşik hem sapma olayı varsa iki kez cezalandırılmaz.
  - system_pattern olayları ceza üretmez (üye metrikler zaten cezalandırıldı) ama renge etki eder.
  - Çok metrikli (ML) olaylar, en yüksek ağırlıklı katkıdaki metriğe atanır.
Renk: skor ≥ green_min → green, ≥ yellow_min → yellow, aksi red;
      aktif critical olay → red, aktif warning olay → en iyi yellow (rules.yaml).
"""

from app.analysis.catalog import Catalog, RulesConfig
from app.analysis.features import SeriesFeatures
from app.models.schemas import SEVERITY_RANK, HealthEvent, OverallStatus, ScorePenalty, SystemScore

STATUS_RANK = {"unknown": 0, "green": 1, "yellow": 2, "red": 3}
NO_PENALTY_DETECTORS = {"rule.system_pattern"}


def primary_metric(e: HealthEvent) -> str | None:
    if not e.contributors:
        return None
    return max(e.contributors, key=lambda c: c.weight).metric


def score_systems(
    events: list[HealthEvent],
    features: dict[str, SeriesFeatures],
    catalog: Catalog,
    rules: RulesConfig,
) -> tuple[list[SystemScore], OverallStatus]:
    """`events`: tek astronotun olayları; `features`: metrik → seri özellikleri."""
    cfg = rules.scoring
    active = [e for e in events if e.status == "active"]
    systems: list[SystemScore] = []
    for info in catalog.system_infos():
        has_data = any(m in features and features[m].frame["value"].notna().any() for m in info.metrics)
        sys_events = [e for e in active if e.system == info.id]
        if not has_data and not sys_events:
            systems.append(SystemScore(system=info.id, display_name=info.display_name, score=None, status="unknown",
                                       metrics=info.metrics, penalties=[]))
            continue
        worst_by_metric: dict[str, HealthEvent] = {}
        for e in sys_events:
            if e.detector in NO_PENALTY_DETECTORS:
                continue
            metric = primary_metric(e)
            if metric is None:
                continue
            cur = worst_by_metric.get(metric)
            if cur is None or cfg.penalties.get(e.severity, 0) > cfg.penalties.get(cur.severity, 0):
                worst_by_metric[metric] = e
        penalties = [
            ScorePenalty(event_id=e.event_id, title=e.title, metric=m, severity=e.severity,
                         penalty=float(cfg.penalties.get(e.severity, 0)))
            for m, e in sorted(worst_by_metric.items(), key=lambda kv: -cfg.penalties.get(kv[1].severity, 0))
        ]
        score = max(0.0, min(100.0, 100.0 - sum(p.penalty for p in penalties)))
        status = "green" if score >= cfg.green_min else "yellow" if score >= cfg.yellow_min else "red"
        worst = max((SEVERITY_RANK[e.severity] for e in sys_events), default=0)
        if worst >= 3 and cfg.critical_forces_red:
            status = "red"
        elif worst >= 2 and cfg.warning_forces_yellow and status == "green":
            status = "yellow"
        systems.append(SystemScore(system=info.id, display_name=info.display_name, score=score, status=status,
                                   metrics=info.metrics, penalties=penalties))

    known = [s for s in systems if s.score is not None]
    if not known:
        return systems, OverallStatus(status="unknown", score=None, worst_system=None)
    overall_status = max((s.status for s in systems), key=lambda st: STATUS_RANK[st])
    worst_sys = min(known, key=lambda s: (s.score, -STATUS_RANK[s.status]))
    return systems, OverallStatus(
        status=overall_status,  # type: ignore[arg-type]
        score=worst_sys.score,
        worst_system=worst_sys.system if worst_sys.status != "green" else None,
    )

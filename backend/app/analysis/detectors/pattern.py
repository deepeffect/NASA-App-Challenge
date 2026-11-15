"""Sistem örüntüsü: aynı sağlık sisteminde birden fazla metrikte eşzamanlı aktif kural olayı.

Çok metrikli olay üretir (contributors + weight). Diğer dedektörlerin ürettiği olaylara bakar,
bu yüzden ANALYSIS_DETECTORS listesinde EN SONDA olmalıdır. Skorlamada ceza üretmez
(aynı metrikleri iki kez saymamak için), ama sistem durum rengini etkiler.
"""

from collections import defaultdict

import numpy as np

from app.analysis.context import AnalysisContext
from app.analysis.detectors.base import register_detector
from app.analysis.episodes import day_start, make_event_id
from app.models.schemas import SEVERITY_RANK, Contributor, DateWindow, HealthEvent

PRIMARY_DETECTORS = ("rule.threshold", "rule.baseline_deviation", "rule.trend")


@register_detector("system_pattern")
class SystemPatternDetector:
    name = "rule.system_pattern"

    def detect(self, ctx: AnalysisContext) -> list[HealthEvent]:
        cfg = ctx.rules.pattern
        min_rank = SEVERITY_RANK[cfg.min_severity]
        groups: dict[tuple[str, str], list[HealthEvent]] = defaultdict(list)
        for e in ctx.events:
            if e.detector in PRIMARY_DETECTORS and e.status == "active" and SEVERITY_RANK[e.severity] >= min_rank:
                groups[(e.astronaut_id, e.system)].append(e)

        out: list[HealthEvent] = []
        for (aid, system), evs in sorted(groups.items()):
            strongest: dict[str, HealthEvent] = {}
            for e in evs:
                metric = e.contributors[0].metric
                cur = strongest.get(metric)
                if cur is None or (SEVERITY_RANK[e.severity], e.score) > (SEVERITY_RANK[cur.severity], cur.score):
                    strongest[metric] = e
            if len(strongest) < cfg.min_metrics:
                continue

            # İlk üyenin başlangıcı (ID kararlılığı için) — olay ilk metrikle başlar, ikincisiyle "oluşur"
            starts = sorted(min(x.window.start for x in evs if x.contributors[0].metric == mm) for mm in strongest)
            start, formed = starts[0], starts[cfg.min_metrics - 1]

            raw: list[tuple[str, float | None, float | None, float | None, float]] = []
            for metric, e in strongest.items():
                sf = ctx.series(aid, metric)
                m = ctx.catalog.metrics[metric]
                last = sf.frame.iloc[-1] if sf is not None else None
                roll = float(last["roll7"]) if last is not None and np.isfinite(last["roll7"]) else e.contributors[0].value
                z7 = float(last["z7"]) if last is not None and np.isfinite(last["z7"]) else e.contributors[0].z
                base = round(sf.baseline.mean, m.decimals + 1) if sf is not None and sf.baseline else None
                strength = abs(z7) if z7 is not None else e.score
                raw.append((metric, None if roll is None else round(roll, m.decimals + 1), base,
                            None if z7 is None else round(z7, 2), max(strength, 1e-6)))
            total = sum(r[4] for r in raw)
            contribs = sorted(
                (Contributor(metric=mt, value=v, baseline=b, z=z, weight=round(s / total, 3),
                             threshold_verified=ctx.catalog.metrics[mt].threshold_verified
                             if ctx.catalog.metrics[mt].has_thresholds else None)
                 for mt, v, b, z, s in raw),
                key=lambda c: -c.weight,
            )
            members = list(strongest.values())
            sev = max(members, key=lambda x: SEVERITY_RANK[x.severity]).severity
            labels = [ctx.catalog.metrics[c.metric].label() for c in contribs]
            out.append(HealthEvent(
                event_id=make_event_id(aid, "rule", self.name, system, start),
                astronaut_id=aid,
                detected_at=day_start(formed),
                source="rule",
                system=system,  # type: ignore[arg-type]
                severity=sev,
                score=round(float(np.mean([x.score for x in members])), 3),
                title=f"{ctx.catalog.system_label(system)}: {len(contribs)} göstergede eşzamanlı olumsuz değişim",
                window=DateWindow(start=start, end=ctx.as_of),
                contributors=contribs,
                status="active",
                detector=self.name,
                description="Aynı dönemde kötüleşen göstergeler: " + ", ".join(labels) + ".",
            ))
        return out

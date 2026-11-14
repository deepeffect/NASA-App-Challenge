/**
 * Tüm astronotlar (200): duruma ve göreve göre filtre, kimlik araması, skora göre sıralama.
 * Satırlar /api/monitor/crew'dan (her astronotun bugünü, Dünya görünümü). Yeni olayda satır vurgulanır.
 */
import { useDeferredValue, useMemo, useState } from "react";

import { useCatalog, useCheckinTimes, useCrew } from "./api";
import { CheckinWhen } from "./CrewSection";
import { flashClass, useLive } from "./live";
import { shareKey, useT } from "./texts";
import { SectionHead, StatusLabel } from "./ui";

type Sort = "score_asc" | "score_desc" | "id";

export function AllAstronauts() {
  const { t, locale } = useT();
  const crew = useCrew();
  const catalog = useCatalog();
  const checkins = useCheckinTimes();
  const { flashFor } = useLive();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<string>("all");
  const [mission, setMission] = useState<string>("all");
  const [sort, setSort] = useState<Sort>("score_asc");
  const q = useDeferredValue(query.trim().toUpperCase());

  const members = useMemo(() => crew.data?.astronauts ?? [], [crew.data]);
  const missions = useMemo(() => {
    const m = new Map<string, string>();
    for (const x of members) m.set(x.astronaut.mission, x.astronaut.mission_label);
    return [...m.entries()].sort((a, b) => a[1].localeCompare(b[1], locale));
  }, [members, locale]);

  const rows = useMemo(() => {
    const out = members.filter(
      (m) =>
        (status === "all" || String(m.status) === status) &&
        (mission === "all" || m.astronaut.mission === mission) &&
        (!q || m.astronaut.id.includes(q)),
    );
    out.sort((a, b) =>
      sort === "id" ? a.astronaut.id.localeCompare(b.astronaut.id) : sort === "score_asc" ? a.score - b.score || a.astronaut.id.localeCompare(b.astronaut.id) : b.score - a.score || a.astronaut.id.localeCompare(b.astronaut.id),
    );
    return out;
  }, [members, status, mission, q, sort]);

  const statuses = catalog.data?.statuses ?? [];

  return (
    <section className="card" aria-labelledby="all-h">
      <SectionHead id="all-h" title={t("allTitle")} />
      <div className="filters" role="search">
        <label>
          {t("search")}
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("searchPh")} autoComplete="off" spellCheck={false} />
        </label>
        <label>
          {t("filterStatus")}
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="all">{t("all")}</option>
            {statuses.map((s, i) => (
              <option key={s} value={String(i)}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("filterMission")}
          <select value={mission} onChange={(e) => setMission(e.target.value)}>
            <option value="all">{t("all")}</option>
            {missions.map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("sortBy")}
          <select value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
            <option value="score_asc">{t("sortScoreAsc")}</option>
            <option value="score_desc">{t("sortScoreDesc")}</option>
            <option value="id">{t("sortId")}</option>
          </select>
        </label>
        <span className="count num" aria-live="polite">
          {t("shown", { n: rows.length, total: members.length })}
        </span>
      </div>
      {crew.isPending ? (
        <p className="state-msg">{t("loading")}</p>
      ) : crew.isError && !crew.data ? (
        <p className="state-msg" role="alert">
          {t("loadError")}{" "}
          <button type="button" onClick={() => void crew.refetch()}>
            {t("retry")}
          </button>
        </p>
      ) : rows.length === 0 ? (
        <p className="state-msg">{t("noMatch")}</p>
      ) : (
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th scope="col">{t("colId")}</th>
                <th scope="col">{t("colMission")}</th>
                <th scope="col">{t("colStatus")}</th>
                <th scope="col" className="r" aria-sort={sort === "id" ? "none" : sort === "score_asc" ? "ascending" : "descending"}>
                  {t("colScore")}
                </th>
                <th scope="col">{t("colGround")}</th>
                <th scope="col">{t("colCheckin")}</th>
                <th scope="col">{t("colNote")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => (
                <tr key={m.astronaut.id} className={flashClass(flashFor(m.astronaut.id)).trim()} data-astronaut={m.astronaut.id}>
                  <td className="id">{m.astronaut.id}</td>
                  <td>{m.astronaut.mission_label}</td>
                  <td>
                    <StatusLabel status={m.status} label={m.status_label} />
                  </td>
                  <td className="r num">{m.score_text}</td>
                  <td>
                    {m.ground ? (
                      <span className="st s2">
                        <span className="glyph g2" aria-hidden="true" />
                        {t("yes")}
                      </span>
                    ) : (
                      <span className="muted">–</span>
                    )}
                  </td>
                  <td>
                    {t(shareKey(m.share))}
                    {m.share && (
                      <span className="muted num">
                        {" "}
                        · <CheckinWhen member={m} checkin={checkins.data?.get(m.astronaut.id)} />
                      </span>
                    )}
                  </td>
                  <td className="wrap">{m.subtitle}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

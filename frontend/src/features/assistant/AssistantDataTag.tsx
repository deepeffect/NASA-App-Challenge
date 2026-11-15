/**
 * Asistan API'sinin hangi astronotun verisiyle çalıştığını gösterir (GET /health -> current).
 * Asistan API'si kendi verisini kullanır (POST /load); sayfadaki astronotla aynı olmayabilir.
 */
import { Tag } from "../../components/ui/Badges";
import { useAssistantHealth } from "./api";
import { useAssistantTexts } from "./texts";

export function AssistantDataTag() {
  const t = useAssistantTexts();
  const h = useAssistantHealth();
  if (h.isPending) return null;
  if (h.isError || !h.data.ok) return <Tag>⚠ {t("offline")}</Tag>;
  const day = h.data.mission_day != null ? t("dataTagDay", { day: h.data.mission_day }) : "";
  return <Tag tone="sky">{t("dataTag", { id: h.data.current ?? "-", day })}</Tag>;
}

/**
 * Asistan API'sinin hangi astronotun verisiyle çalıştığını gösterir (GET /health -> current).
 * Asistan API'si kendi verisini kullanır (POST /load); sayfadaki astronotla aynı olmayabilir.
 */
import { Tag } from "../../components/ui/Badges";
import { useAssistantHealth } from "./api";

export function AssistantDataTag() {
  const h = useAssistantHealth();
  if (h.isPending) return null;
  if (h.isError || !h.data.ok) return <Tag>⚠ Assistant offline</Tag>;
  const day = h.data.mission_day != null ? ` · day ${h.data.mission_day}` : "";
  return (
    <Tag tone="sky">
      Assistant data: {h.data.current ?? "-"}
      {day}
    </Tag>
  );
}

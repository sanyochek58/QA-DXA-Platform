import { Stethoscope } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { StudyPage } from "../api/types";
import { EmptyState, ErrorNote, PageHeader } from "../components/ui";
import { plural } from "../lib/format";
import { ListSkeleton, StudyList } from "./Studies";

export function Queue() {
  const { data, isPending, error } = useQuery({
    queryKey: ["queue"],
    queryFn: () => api<StudyPage>("/studies/queue"),
    refetchInterval: 15_000,
  });
  return (
    <>
      <PageHeader
        title="На проверку"
        subtitle={
          data?.total
            ? `${data.total} ${plural(data.total, "исследование ждёт", "исследования ждут", "исследований ждут")} вашего решения. Оно становится итоговым.`
            : "Сомнительные случаи, которые система передала врачу."
        }
      />
      {error && <div className="mb-4"><ErrorNote>{(error as Error).message}</ErrorNote></div>}
      {isPending ? (
        <ListSkeleton />
      ) : data && data.items.length ? (
        <StudyList items={data.items} showOperator />
      ) : (
        <div className="card">
          <EmptyState icon={<Stethoscope size={40} />} title="Очередь пуста"
            text="Все сомнительные исследования разобраны. Новые появятся здесь сами." />
        </div>
      )}
    </>
  );
}

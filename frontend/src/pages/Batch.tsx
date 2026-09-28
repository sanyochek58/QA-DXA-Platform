import { DownloadSimple, FileZip, SpinnerGap, X } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { useDropzone } from "react-dropzone";
import { tokenStore } from "../api/client";
import { ErrorNote, PageHeader } from "../components/ui";

const OUTPUT = [
  ["results.xlsx, results.csv", "одна строка на снимок: область, класс качества (0/1), типы нарушений, статус, время"],
  ["series/", "дополнительная DICOM-серия с визуализацией нарушений для каждого исследования"],
];

/** Пакетная проверка архива: результат не сохраняется в системе, а отдаётся одним zip. */
export function Batch() {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ url: string; size: number; seconds: number } | null>(null);

  useEffect(() => () => { if (result) URL.revokeObjectURL(result.url); }, [result]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: (accepted) => {
      setError(null);
      setResult(null);
      setFile(accepted[0] ?? null);
    },
    multiple: false,
    accept: { "application/zip": [".zip"] },
  });

  async function run() {
    if (!file) return setError("Выберите zip-архив с исследованиями");
    setBusy(true);
    setError(null);
    const started = performance.now();
    try {
      const fd = new FormData();
      fd.append("archive", file);
      const token = tokenStore.get();
      const resp = await fetch("/api/v1/studies/batch", {
        method: "POST",
        body: fd,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!resp.ok) {
        let detail = `Ошибка сервера (${resp.status})`;
        try {
          detail = (await resp.json()).detail ?? detail;
        } catch {
          /* ответ не JSON */
        }
        throw new Error(detail);
      }
      const blob = await resp.blob();
      setResult({ url: URL.createObjectURL(blob), size: blob.size, seconds: (performance.now() - started) / 1000 });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось обработать архив");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Пакетная проверка"
        subtitle="Архив с любым числом исследований превращается в отчёт в формате конкурса. В рабочий список отделения ничего не попадает."
      />
      <div className="grid gap-5 lg:grid-cols-[1.5fr_1fr] items-start">
        <div className="flex flex-col gap-5">
          <div
            {...getRootProps()}
            className={`card px-6 py-14 text-center cursor-pointer border-2 border-dashed transition-colors duration-150 ${
              isDragActive ? "border-brand bg-brand-soft" : "border-line-strong hover:border-brand/50"
            }`}
          >
            <input {...getInputProps()} aria-label="Выбрать zip-архив" />
            <FileZip size={44} weight="light" className="mx-auto text-brand" />
            <p className="mt-4 text-[17px] font-semibold">{isDragActive ? "Отпустите архив" : "Перетащите zip-архив сюда"}</p>
            <p className="mt-1 text-[15px] text-muted">Папки внутри могут быть любой вложенности. Исследования группируются по DICOM-тегам.</p>
          </div>

          {file && (
            <div className="card px-5 h-14 flex items-center gap-3 fade-in">
              <FileZip size={22} className="text-muted shrink-0" />
              <span className="flex-1 truncate text-[15px]">{file.name}</span>
              <span className="text-[13px] text-muted tnum">{(file.size / 1024 / 1024).toFixed(1)} МБ</span>
              <button className="size-7 grid place-items-center rounded-full bg-fill text-muted hover:text-bad" aria-label="Убрать файл"
                onClick={() => { setFile(null); setResult(null); }}>
                <X size={13} weight="bold" />
              </button>
            </div>
          )}

          {error && <ErrorNote>{error}</ErrorNote>}

          {result ? (
            <div className="card p-5 flex flex-col sm:flex-row sm:items-center gap-4 fade-in">
              <div className="flex-1">
                <p className="text-[17px] font-semibold">Отчёт готов</p>
                <p className="text-[15px] text-muted">
                  Обработано за {result.seconds.toFixed(1)} с · {(result.size / 1024 / 1024).toFixed(1)} МБ
                </p>
              </div>
              <a href={result.url} download="dxa_qa_results.zip" className="btn-primary">
                <DownloadSimple size={18} weight="bold" /> Скачать результаты
              </a>
            </div>
          ) : (
            <button className="btn-primary h-12" onClick={run} disabled={busy || !file}>
              {busy ? (
                <>
                  <SpinnerGap size={18} className="animate-spin" /> Обрабатываем архив
                </>
              ) : (
                "Запустить проверку"
              )}
            </button>
          )}
        </div>

        <section>
          <h2 className="text-[13px] font-medium text-muted px-1 mb-2">Что будет в результате</h2>
          <ul className="card overflow-hidden">
            {OUTPUT.map(([name, text]) => (
              <li key={name} className="px-5 py-3.5 border-b border-line last:border-0">
                <div className="text-[15px] font-semibold font-mono">{name}</div>
                <div className="text-[14px] text-muted mt-0.5">{text}</div>
              </li>
            ))}
          </ul>
          <p className="mt-2 px-1 text-[13px] text-muted">
            То же без интерфейса: <code className="text-ink-2">./run_batch.sh архив.zip</code> или{" "}
            <code className="text-ink-2">POST /v1/batch</code> ML-сервиса.
          </p>
        </section>
      </div>
    </>
  );
}

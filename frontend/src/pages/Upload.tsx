import { CaretRight, FileArrowUp, FileText, X } from "@phosphor-icons/react";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useDropzone } from "react-dropzone";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { api, ApiError } from "../api/client";
import type { Study } from "../api/types";
import { ErrorNote, PageHeader } from "../components/ui";
import { plural } from "../lib/format";

const CHECKS = [
  "Укладка и ось позвоночника",
  "Посторонние предметы в поле",
  "Ротация бедра",
  "Область интересов бедра",
];

export function Upload() {
  const navigate = useNavigate();
  const { can } = useAuth();
  const [files, setFiles] = useState<File[]>([]);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: (accepted) => {
      setError(null);
      setFiles((prev) => {
        const seen = new Set(prev.map((f) => f.name + f.size));
        return [...prev, ...accepted.filter((f) => !seen.has(f.name + f.size))].slice(0, 40);
      });
    },
    multiple: true,
  });

  const upload = useMutation({
    mutationFn: async () => {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      if (title.trim()) fd.append("title", title.trim());
      return api<Study>("/studies", { method: "POST", body: fd });
    },
    onSuccess: (s) => navigate(`/studies/${s.id}`),
    onError: (e) => setError(e instanceof ApiError ? e.message : "Не удалось загрузить исследование"),
  });

  function submit() {
    if (!files.length) return setError("Добавьте хотя бы один DICOM-файл");
    upload.mutate();
  }

  const size = files.reduce((s, f) => s + f.size, 0);

  return (
    <>
      <PageHeader title="Новое исследование" subtitle="Добавьте все снимки одного пациента сразу: позвоночник и оба бедра." />

      <div className="grid gap-5 lg:grid-cols-[1.5fr_1fr] items-start">
        <div className="flex flex-col gap-5">
          <div
            {...getRootProps()}
            className={`card px-6 py-16 text-center cursor-pointer border-2 border-dashed transition-colors duration-150 ${
              isDragActive ? "border-brand bg-brand-soft" : "border-line-strong hover:border-brand/50"
            }`}
          >
            <input {...getInputProps()} aria-label="Выбрать DICOM-файлы" />
            <FileArrowUp size={44} weight="light" className="mx-auto text-brand" />
            <p className="mt-4 text-[17px] font-semibold">
              {isDragActive ? "Отпустите, чтобы добавить" : "Перетащите файлы сюда"}
            </p>
            <p className="mt-1 text-[15px] text-muted">или нажмите, чтобы выбрать. DICOM, до 40 файлов.</p>
          </div>

          {files.length > 0 && (
            <section className="fade-in">
              <div className="flex items-baseline justify-between px-1 mb-2">
                <h2 className="text-[13px] font-medium text-muted">
                  {files.length} {plural(files.length, "файл", "файла", "файлов")} · {(size / 1024 / 1024).toFixed(1)} МБ
                </h2>
                <button className="text-[15px] text-brand font-medium" onClick={() => setFiles([])}>Очистить</button>
              </div>
              <ul className="card overflow-hidden max-h-72 overflow-y-auto">
                {files.map((f, i) => (
                  <li key={f.name + f.size} className="flex items-center gap-3 px-5 h-12 border-b border-line last:border-0">
                    <FileText size={20} className="text-faint shrink-0" />
                    <span className="truncate flex-1 text-[15px]">{f.name}</span>
                    <span className="text-[13px] text-muted tnum">{Math.round(f.size / 1024)} КБ</span>
                    <button className="size-7 grid place-items-center rounded-full bg-fill text-muted hover:text-bad" aria-label={`Убрать ${f.name}`}
                      onClick={() => setFiles(files.filter((_, j) => j !== i))}>
                      <X size={13} weight="bold" />
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>

        <div className="flex flex-col gap-5">
          <section className="card p-5 flex flex-col gap-4">
            <div>
              <label className="label" htmlFor="title">Метка</label>
              <input id="title" className="input" placeholder="Например, кабинет 2, 14:30" value={title}
                maxLength={255} onChange={(e) => setTitle(e.target.value)} />
              <p className="mt-1.5 px-1 text-[13px] text-muted">Необязательно. Персональные данные пациента не вводите.</p>
            </div>
            {error && <ErrorNote>{error}</ErrorNote>}
            <button className="btn-primary h-12" onClick={submit} disabled={upload.isPending}>
              {upload.isPending ? "Загружаем" : "Проверить качество"}
            </button>
          </section>

          <section>
            <h2 className="text-[13px] font-medium text-muted px-1 mb-2">Что проверяется</h2>
            <ul className="card overflow-hidden">
              {CHECKS.map((c) => (
                <li key={c} className="px-5 py-3 text-[15px] border-b border-line last:border-0">{c}</li>
              ))}
            </ul>
            <p className="mt-2 px-1 text-[13px] text-muted">Сомнительные случаи автоматически уходят врачу.</p>
            {can("radiologist", "admin") && (
              <Link to="/batch" className="mt-4 card px-5 py-3.5 flex items-center justify-between text-[15px] hover:bg-surface/70">
                <span>Проверить целый архив исследований</span>
                <CaretRight size={16} weight="bold" className="text-line-strong" />
              </Link>
            )}
          </section>
        </div>
      </div>
    </>
  );
}

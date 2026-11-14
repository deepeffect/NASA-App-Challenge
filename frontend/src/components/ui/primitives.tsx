import type { UseQueryResult } from "@tanstack/react-query";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { ApiError } from "../../api/client";

export function Card({
  title,
  actions,
  children,
  className = "",
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-2xl border border-slate-800 bg-slate-900/70 p-5 ${className}`}>
      {(title || actions) && (
        <header className="mb-4 flex items-center justify-between gap-3">
          {title && <h2 className="text-lg font-semibold text-slate-100">{title}</h2>}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

const VARIANTS = {
  primary: "bg-sky-500 text-slate-950 hover:bg-sky-400 disabled:bg-slate-700 disabled:text-slate-400",
  secondary: "border border-slate-600 bg-slate-800 text-slate-100 hover:bg-slate-700 disabled:opacity-50",
  ghost: "text-slate-300 hover:bg-slate-800 disabled:opacity-50",
  danger: "border border-red-500/70 bg-red-950/60 text-red-200 hover:bg-red-900/60 disabled:opacity-50",
};

export function Button({
  variant = "secondary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: keyof typeof VARIANTS }) {
  return (
    <button
      type="button"
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 py-2 font-medium transition-colors disabled:cursor-not-allowed ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  );
}

export function Spinner({ label = "Yükleniyor…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-slate-400" role="status">
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-slate-600 border-t-sky-400" />
      <span>{label}</span>
    </div>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  const msg =
    error instanceof ApiError
      ? `${error.status}: ${error.message}`
      : error instanceof Error
        ? error.message
        : "Bilinmeyen hata";
  return (
    <div role="alert" className="rounded-xl border border-red-500/60 bg-red-950/50 p-4 text-red-200">
      Veri alınamadı — {msg}
    </div>
  );
}

/** Sorgu durumlarını (yükleniyor / hata / veri) tek yerde ele alır. */
export function QueryState<T>({
  query,
  children,
  loadingLabel,
}: {
  query: UseQueryResult<T>;
  children: (data: T) => ReactNode;
  loadingLabel?: string;
}) {
  if (query.isPending) return <Spinner label={loadingLabel} />;
  if (query.isError) return <ErrorBox error={query.error} />;
  return <>{children(query.data)}</>;
}

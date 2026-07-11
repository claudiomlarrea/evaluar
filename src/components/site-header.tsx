import Link from "next/link";

export function SiteHeader() {
  return (
    <header className="border-b border-slate-200 bg-white/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
        <Link href="/" className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-teal-600 text-lg font-bold text-white">
            E
          </div>
          <div>
            <p className="text-lg font-semibold text-slate-900">EvaluAR</p>
            <p className="text-xs text-slate-500">
              Examen en papel. Corrección digital.
            </p>
          </div>
        </Link>
        <nav className="flex items-center gap-3 text-sm">
          <Link
            href="/docente"
            className="rounded-lg px-3 py-2 text-slate-600 hover:bg-slate-100"
          >
            Docentes
          </Link>
          <Link
            href="/docente/panel"
            className="rounded-lg bg-teal-600 px-4 py-2 font-medium text-white hover:bg-teal-700"
          >
            Panel
          </Link>
        </nav>
      </div>
    </header>
  );
}

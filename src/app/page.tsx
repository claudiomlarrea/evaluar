import Link from "next/link";
import { SiteHeader } from "@/components/site-header";
import { Button, Card } from "@/components/ui";

export default function HomePage() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-teal-50">
      <SiteHeader />
      <main className="mx-auto max-w-6xl px-4 py-16">
        <div className="grid gap-10 lg:grid-cols-2 lg:items-center">
          <div className="space-y-6">
            <p className="inline-flex rounded-full bg-teal-100 px-3 py-1 text-sm font-medium text-teal-800">
              Evaluación presencial híbrida
            </p>
            <h1 className="text-4xl font-bold tracking-tight text-slate-900 md:text-5xl">
              EvaluAR
            </h1>
            <p className="text-lg leading-8 text-slate-600">
              Los alumnos rinden en papel. Después cargan sus respuestas desde
              el celular. El docente sube la clave de respuestas y el sistema
              corrige al instante: nota, DNI, preguntas falladas y estadísticas
              por ítem.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link href="/docente">
                <Button>Soy docente</Button>
              </Link>
              <Link href="/docente/panel/nuevo">
                <Button variant="secondary">Crear examen</Button>
              </Link>
            </div>
          </div>

          <div className="grid gap-4">
            <Card title="Flujo en el aula">
              <ol className="space-y-3 text-sm text-slate-600">
                <li>1. El docente crea el examen y carga la rúbrica.</li>
                <li>2. Se genera un link/QR para la sesión del examen.</li>
                <li>3. Los alumnos rinden en papel y se recogen cuadernillos.</li>
                <li>4. Cada alumno marca sus respuestas en el link.</li>
                <li>5. El sistema entrega nota al alumno y planilla al docente.</li>
              </ol>
            </Card>
            <Card title="Para carreras con alto volumen">
              <p className="text-sm text-slate-600">
                Pensado para casos como Medicina: 100 alumnos, 50 preguntas,
                opción múltiple, V/F y emparejamiento. De 20.000 correcciones
                manuales a cero.
              </p>
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
}

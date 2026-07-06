# EvaluAR

**Examen en papel. Corrección digital.**

Sistema híbrido de evaluación presencial para universidades. Los alumnos rinden en papel y, tras recoger los cuadernillos, cargan sus respuestas desde el celular. El docente sube la clave de respuestas y el sistema corrige al instante.

## Despliegue en Streamlit Cloud

1. Subí este repositorio a GitHub.
2. Entrá a [share.streamlit.io](https://share.streamlit.io).
3. **New app** → elegí el repo `evaluar`.
4. **Main file path:** `app.py`
5. Deploy.

### Link para alumnos

Cada sesión genera un código (ej. `ABC12345`). El link del alumno es:

```
https://TU-APP.streamlit.app/?code=ABC12345
```

## Uso local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Persistencia (PostgreSQL) — obligatorio en producción

**Problema:** En Streamlit Cloud, SQLite se **borra en cada redeploy**. Los docentes pierden su cuenta y los exámenes desaparecen.

**Solución:** Base PostgreSQL gratuita (5 minutos):

### Opción recomendada: [Neon](https://neon.tech)

1. Creá cuenta en [neon.tech](https://neon.tech) → **New project** → nombre `evaluar`.
2. En el panel, copiá la **connection string** (formato `postgresql://usuario:pass@host/evaluar?sslmode=require`).
3. En [share.streamlit.io](https://share.streamlit.io) → tu app → **Settings** → **Secrets**:

```toml
DATABASE_URL = "postgresql://usuario:contraseña@ep-xxxx.us-east-2.aws.neon.tech/evaluar?sslmode=require"
```

4. **Save** → **Reboot app**.
5. En la barra lateral debe decir `Base de datos: PostgreSQL`.
6. Volvé a **Crear cuenta** docente (una sola vez). Desde ahí, todo persiste.

Alternativas: Supabase, Railway, ElephantSQL.

## Flujo

1. **Docente** → Crear cuenta → Nuevo examen → clave de respuestas pregunta por pregunta.
2. **Generar código del parcial** → compartir link, QR o WhatsApp.
3. **Alumnos** → Rinden en papel → cargan respuestas con el código.
4. **Docente** → Cierra la carga cuando termina la comisión → planilla y Excel.

## Stack

- Python 3.10+
- Streamlit
- SQLite o PostgreSQL

## Licencia

MIT

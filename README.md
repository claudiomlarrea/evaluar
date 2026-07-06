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

## Persistencia (PostgreSQL)

Sin configuración extra, EvaluAR usa **SQLite** (ideal en local). En Streamlit Cloud los datos pueden perderse al reiniciar.

Para producción, configurá **PostgreSQL** (Neon, Supabase, Railway, etc.):

1. Creá una base PostgreSQL y copiá la URL de conexión.
2. En Streamlit Cloud → **Settings → Secrets**, agregá:

```toml
DATABASE_URL = "postgresql://usuario:contraseña@host:5432/evaluar"
```

3. Reiniciá la app. En la barra lateral verás `Base de datos: PostgreSQL`.

Plantilla local: `.streamlit/secrets.toml.example`

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

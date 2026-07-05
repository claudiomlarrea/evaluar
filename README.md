# EvaluAR

**Examen en papel. Corrección digital.**

Sistema híbrido de evaluación presencial para universidades. Los alumnos rinden en papel y, tras recoger los cuadernillos, cargan sus respuestas desde el celular. El docente sube la clave de respuestas y el sistema corrige al instante.

## Despliegue en Streamlit Cloud

1. Subí este repositorio a GitHub.
2. Entrá a [share.streamlit.io](https://share.streamlit.io).
3. **New app** → elegí el repo `evaluar`.
4. **Main file path:** `streamlit_app.py`
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

## Flujo

1. **Docente** → Crear cuenta → Nuevo examen → pegar clave de respuestas (una por línea).
2. **Generar sesión** → copiar link `?code=XXXX`.
3. **Alumnos** → Rinden en papel → abren el link → cargan respuestas.
4. **Docente** → Ve planilla con nombre, DNI, nota e ítems fallados → exporta CSV.

## Nota sobre persistencia

En Streamlit Cloud el almacenamiento SQLite es **efímero**: los datos pueden perderse al reiniciar la app. Para producción institucional conviene migrar a PostgreSQL (Supabase, Neon, etc.).

## Stack

- Python 3.10+
- Streamlit
- SQLite

## Licencia

MIT

# SimplyApply — estado del proyecto

Última actualización: 2026-09-02 (sesión 2: cover letter + extensión Firefox)

## Extensión Firefox (autofill + cover letter) — NUEVO

- Directorio: `firefox-extension/` (raíz del repo, sin build step, JS plano).
- Qué hace: en una página de aplicación real (Greenhouse/Lever/Workday), rellena campos de datos personales y pega una cover letter generada localmente. Si SimplyApply no conoce la oferta (llegaste vía LinkedIn/Indeed, no por su búsqueda), el popup deja pegar la descripción y crea el job al vuelo (`POST /api/jobs/adhoc`). Nunca envía el formulario — el usuario hace click en Submit.
- **Instalar**: Firefox → `about:debugging#/runtime/this-firefox` → "Load Temporary Add-on" → seleccionar `firefox-extension/manifest.json`. Se pierde al reiniciar Firefox (temporal); recargar cuando haga falta.
- **Configurar el token (obligatorio, una vez)**: el backend exige un header `X-SimplyApply-Token` en los endpoints que usa la extensión (protección añadida tras auditoría de seguridad — ver abajo). Token actual (leído directo de la base de datos activa en `backend/data/`):
  ```
  nWRaUfrxfe6zcMSwyy2ErFegIqgTchinSlfmM9e6L6o
  ```
  Pegar en el icono de la extensión → Options. **Ojo**: si algún día se borra `backend/data/simplyapply.db` o se arranca el backend por primera vez en otra máquina, se genera un token nuevo — leerlo del log de arranque de uvicorn o repetir la consulta de abajo:
  ```bash
  cd backend && .venv/bin/python -c "
  from app.db import SessionLocal; from app.models import Setting
  print(SessionLocal().get(Setting, 'extension_token').value)"
  ```
- **Verificado end-to-end por curl** (no en navegador real — sin herramienta de navegador conectada en esta sesión): ad-hoc job → apply → cover-letter → by-url, los 4 con 200 y datos correctos; 401 sin token confirmado.
- **NO verificado**: selectores de campos reales en Greenhouse/Lever/Workday (`firefox-extension/content/*.js`) — son heurísticas basadas en convenciones documentadas, marcadas explícitamente `SELECTORS UNVERIFIED` en cada archivo. Cargar la extensión y probar en una oferta real antes de confiar en el autofill.
- **Limitación conocida y aceptada**: subir el fichero de CV no se puede automatizar (los navegadores bloquean asignar `input[type=file]` por script) — la extensión resalta el campo y muestra el nombre del fichero a adjuntar a mano.
- **Workday**: solo cubre la primera pantalla ("Personal Information"). El asistente multi-página (Experience/Education con listas dinámicas) queda fuera de alcance, documentado en `firefox-extension/README.md` — cada tenant de Workday personaliza su DOM, no hay un selector único posible sin verlo en vivo.

### Auditoría de seguridad (dc-security, opus) — 2 HIGH encontrados y corregidos

1. El guardrail no protegía `basics` (nombre/email/teléfono/URLs/perfiles) — una oferta maliciosa podía hacer que el modelo reescribiera el contacto del CV tailored sin disparar ninguna violación. Corregido: `guardrail.py` ahora compara `basics` campo a campo contra el CV base (kind=`"contact"`), mismo mecanismo de retry+fallback que ya existía para el resto.
2. CORS permitía a cualquier extensión instalada (no solo la nuestra) leer el CV y reescribir `PUT /api/settings` para redirigir el tráfico del LLM (y la API key, si se usa OpenAI) de forma persistente. Corregido con el token `X-SimplyApply-Token` de arriba — CORS por sí solo nunca fue una barrera de autenticación real.
- Tests: 84/84 passed (58 originales + 26 nuevos entre las dos rondas).

## Setup

- Repo clonado en `~/Projects/TRABAJO/simply-apply` desde github.com/artbyjazi/simply-apply.
- Backend: venv Python 3.12 en `backend/.venv`, deps instaladas (`pip install -r requirements.txt`).
- Frontend: `npm install` hecho en `frontend/`.
- `.env` copiado de `.env.example` en la raíz del repo.
- Tests backend: `cd backend && .venv/bin/python -m pytest` → 58/58 passed.

## Cómo arrancarlo

```bash
# backend
cd ~/Projects/TRABAJO/simply-apply/backend
.venv/bin/uvicorn app.main:app --port 8000

# frontend (otra terminal)
cd ~/Projects/TRABAJO/simply-apply/frontend
npm run dev
```

- Backend: http://localhost:8000
- Frontend: http://localhost:3000
- Última vez comprobado, ambos corrían en background (`&` + `disown`) — confirmar que siguen vivos con `curl -s localhost:8000/docs` / `curl -s localhost:3000` antes de usarlo, si no, relanzar con lo de arriba.

## Configuración de IA

- **Proveedor: Ollama local**, no Anthropic — decisión explícita del usuario para no depender de una API key de pago.
- `.env`: `SIMPLYAPPLY_LLM_PROVIDER=ollama`, `SIMPLYAPPLY_OLLAMA_MODEL=qwen3:8b`, `SIMPLYAPPLY_OLLAMA_HOST=http://localhost:11434`.
- Confirmado activo vía `GET /api/settings` → `{"llm_provider":"ollama","model":"qwen3:8b","has_key":false,...}`.
- Se eligió `qwen3:8b` sobre `qwen2.5-coder:14b`/`14b-16k` (también instalados) porque tailoring/parsing de CV es extracción estructurada + reescritura de prosa, no código — el modelo coder no es la herramienta correcta aquí aunque sea más grande. `nomic-embed-text` también instalado pero no lo usa esta app.
- Aviso del propio README: modelos locales pequeños cometen más errores de parseo que Anthropic → revisar bien la pantalla de confirmación tras subir el CV o tras cada tailor().

## CV / datos del usuario

- CV fuente: `~/Projects/TRABAJO/resume-1.pdf` (Adrián Pliego Pérez, AI/ML/Backend Engineer, Madrid).
- Enlaces: portfolio https://adrian-pliego.vercel.app/, LinkedIn https://www.linkedin.com/in/adrianpliegoperez/, GitHub https://github.com/adro0303, email adroplpe@gmail.com.
- Pendiente: subir el CV en la UI (Settings/onboarding) para que lo parsee a JSON Resume y revisar la pantalla de confirmación con los datos completos del PDF.

## Qué hace realmente la herramienta

No auto-rellena ni envía solicitudes. Flujo: buscar ofertas (Greenhouse por empresa + Arbeitnow remoto/EU) → elegir una → `tailor()` regenera CV desde los datos estructurados → guardrail en código (`backend/app/services/guardrail.py`) verifica que no se inventó ningún empleador/título/fecha/métrica/skill (whitelist contra el CV base, reintenta una vez, si vuelve a fallar devuelve el CV original + aviso) → genera DOCX (para ATS) + PDF de una página → da un enlace "Apply" que el usuario abre y rellena manualmente.

## Pendiente / próximos pasos

- [x] Subir CV y validar el parseo a JSON Resume — el parseo automático (`/api/resumes/parse` con qwen3:8b) dejó `basics`/`work`/`education`/`skills` vacíos, solo acertó `projects`. Se construyó el JSON a mano desde `extracted_text` (correcto) y se guardó como base vía `POST /api/resumes` (resume id=1, `is_base=true`, 3 work, 3 education, 5 skills, 4 projects).
- [x] Probar `tailor()` end to end (`POST /api/apply/{job_id}` sobre "Fullstack Software Engineer - Core" @ dataiku, arbeitnow) — **qwen3:8b falla el guardrail de forma consistente**: 61 violaciones en el intento 1 (universidad inventada "University of Lisbon", proyectos inventados, skills inventadas como "Apache Spark"/"ETL Processes", métrica "30%" inventada), reintento también falló. El guardrail funcionó correctamente: descartó todo y usó el CV original sin modificar (`fell_back: true`) en vez de arriesgar contenido inventado. `application_id=1`, `resume_id=2` (= CV original, no tailored), docx/pdf descargables y verificados (200 OK).
- [ ] **Decisión pendiente con el usuario:** `qwen3:8b` no es fiable para el paso de tailoring (aunque sí sirvió para parseo... no, tampoco — falló ahí también). Opciones: (a) aceptar que cada `tailor()` caerá al CV original sin personalizar (el guardrail lo hace seguro pero inútil como "tailoring"), (b) probar `qwen2.5-coder:14b` u otro modelo local más grande, (c) cambiar el proveedor a Anthropic solo para este paso (contradice la decisión explícita de usar Ollama local para no depender de una key de pago).
- [ ] Aplicar manualmente a la oferta de dataiku vía su apply_url: https://www.arbeitnow.com/jobs/companies/dataiku/remote-fullstack-software-engineer-core-437469 (el tool no auto-envía, solo prepara CV + enlace).
- [ ] Si `docker compose up` se llega a probar, actualizar aquí (a día de hoy no verificado por el autor).

# Pixora

Pixora es una aplicación para compartir fotografías y explorar ideas para
sesiones fotográficas. Incluye un cliente de escritorio construido con Flet,
una API REST con FastAPI y persistencia repartida entre PostgreSQL y MongoDB.
La generación de recomendaciones puede ejecutarse localmente con Ollama o
conectarse a Gemini.

## Contenido

- [Funciones](#funciones)
- [Arquitectura](#arquitectura)
- [Requisitos](#requisitos)
- [Instalación y configuración](#instalación-y-configuración)
- [Ejecución](#ejecución)
- [Pruebas](#pruebas)
- [API principal](#api-principal)
- [Datos y persistencia](#datos-y-persistencia)
- [Solución de problemas](#solución-de-problemas)
- [Entrega y manejo seguro de credenciales](#entrega-y-manejo-seguro-de-credenciales)

## Funciones

- Registro e inicio de sesión mediante usuario o correo electrónico.
- Contraseñas almacenadas como hashes scrypt y sesiones autenticadas con JWT.
- Feed con fotografías, likes persistentes, creación de publicaciones y
  eliminación de publicaciones propias.
- Almacenamiento de fotografías y detalles asociados en MongoDB.
- Búsqueda de recomendaciones de lugares y poses para sesiones fotográficas.
- Generación de recomendaciones con Ollama local o Gemini, con respuestas
  estructuradas de respaldo si el proveedor de IA no está disponible.

## Arquitectura

```text
Cliente Flet (app.py, src/)
        │ HTTP + JWT
        ▼
API FastAPI (backend/main.py)
        ├── PostgreSQL: cuentas, publicaciones, ubicaciones y tipos de sesión
        ├── MongoDB (pixora_db): fotografías, detalles, comentarios y likes
        └── Ollama local o Google Gemini: recomendaciones
```

- `app.py`: inicio de la interfaz y navegación.
- `src/controllers/`: lógica de autenticación, feed y comunicación desde la UI.
- `src/views/`: pantallas construidas con Flet.
- `src/services/api_client.py`: cliente HTTP y manejo de errores de la API.
- `backend/main.py`: rutas HTTP, autenticación y coordinación de servicios.
- `backend/postgres_access.py` y `backend/mongo_access.py`: acceso a las bases
  de datos.
- `tests/`: pruebas automatizadas de controladores, API y persistencia.

El cliente se comunica únicamente con la API. Las credenciales de PostgreSQL,
MongoDB y Gemini deben permanecer en el entorno del backend; no se deben
incrustar en la aplicación Flet.

## Requisitos

- Windows, macOS o Linux.
- Python 3.10 o posterior (el entorno de desarrollo del proyecto se ha probado
  con Python 3.14).
- PostgreSQL con el esquema de Pixora ya preparado.
- MongoDB con una base de datos accesible para la aplicación.
- Ollama para recomendaciones locales, o una clave de Google AI Studio si se
  desea utilizar Gemini.

Las dependencias Python del proyecto están en `requirements.txt`. Las
dependencias adicionales para ejecutar pruebas están en
`requirements-dev.txt`.

## Instalación y configuración

### 1. Descargar el proyecto y crear el entorno Python

Desde PowerShell, sitúate en la carpeta raíz del proyecto:

```powershell
py -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

En macOS o Linux, activa el entorno con `source venv/bin/activate` y sustituye
`.\venv\Scripts\python.exe` en los comandos posteriores por `python`.

### 2. Crear y completar `.env`

Copia la plantilla incluida:

```powershell
Copy-Item .env.example .env
```

Edita `.env` en la raíz del proyecto y reemplaza los marcadores por valores
válidos. La plantilla no contiene credenciales funcionales.

| Variable | Uso |
| --- | --- |
| `POSTGRES_DSN` | Conexión del backend a PostgreSQL, por ejemplo `postgresql://USUARIO:CONTRASENA@HOST:5432/BASE`. |
| `PIXORA_AUTH_SECRET` | Secreto privado para firmar los JWT. Genera uno distinto para cada instalación. |
| `MONGODB_URI` | URI de conexión al servidor o clúster de MongoDB. |
| `MONGODB_DATABASE` | Base MongoDB de Pixora; normalmente `pixora_db`. |
| `AI_PROVIDER` | Proveedor de recomendaciones: `ollama` o `gemini`. |
| `OLLAMA_BASE_URL` | URL del servidor Ollama, normalmente `http://127.0.0.1:11434`. |
| `OLLAMA_MODEL` | Modelo de texto disponible en Ollama, por defecto `qwen2.5:3b`. |
| `GEMINI_API_KEY` | Clave privada de Google AI Studio; solo necesaria con Gemini. |
| `GEMINI_TEXT_MODEL` | Modelo Gemini de texto, por defecto `gemini-2.5-flash`. |
| `GEMINI_EMBEDDING_MODEL` | Modelo de embeddings Gemini configurado en el entorno. |
| `FRONTEND_ORIGINS` | Orígenes web permitidos por CORS, separados por comas. |

Genera un secreto de autenticación aleatorio desde PowerShell:

```powershell
.\venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copia el resultado en `PIXORA_AUTH_SECRET`. No uses la contraseña de PostgreSQL
ni una clave de Gemini como secreto JWT.

### 3. Preparar las bases de datos

El proyecto espera una base PostgreSQL existente con las tablas y columnas de
Pixora. No crea el esquema ni ejecuta migraciones automáticamente. La base debe
contener, entre otras, las tablas `usuarios`, `publicaciones`, `seguidores`,
`localizaciones` y `tipo_sesion_fotografica`, con las relaciones y restricciones
que usa la aplicación. Los identificadores que la aplicación omite al insertar
deben generarse en la base.

MongoDB debe tener la base indicada en `MONGODB_DATABASE` y las colecciones
esperadas ya creadas: `CONTENEDORES_FOTOGRAFÍAS`,
`DETALLES_PUBLICACIONES`, `COMENTARIOS_COMUNIDAD`,
`GALERÍAS_UBICACIONES` y `POSES_MODELOS`. El backend comprueba la configuración
al acceder; no inicializa automáticamente un clúster o sus colecciones.

El profesor necesita acceso a bases preparadas para Pixora. Se pueden usar
servicios propios o credenciales de prueba facilitadas por un canal privado;
no incluyas contraseñas, URI completas con credenciales ni volcados de datos
privados en GitHub o Drive.

### 4. Configurar la inteligencia artificial

**Ollama local (opción predeterminada):**

1. Instala Ollama desde [ollama.com](https://ollama.com/).
2. Descarga el modelo configurado en `.env`:

   ```powershell
   ollama pull qwen2.5:3b
   ```

3. Inicia Ollama y conserva `AI_PROVIDER=ollama`.
4. Comprueba que `OLLAMA_BASE_URL` apunta al equipo donde se ejecuta Ollama.

El servicio de Ollama debe estar disponible para el backend en el momento de
solicitar recomendaciones. No se necesita una clave de proveedor externo para
esta opción.

**Gemini (opcional):**

1. Obtén una clave de Google AI Studio.
2. Configura `AI_PROVIDER=gemini` y pega la clave en `GEMINI_API_KEY`.
3. Confirma que `GEMINI_TEXT_MODEL` contiene un modelo habilitado en la cuenta.

No publiques la clave ni la incluyas en capturas, logs o documentación.

## Ejecución

Abre dos terminales en la raíz del proyecto. Primero, inicia la API:

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

Luego, inicia el cliente:

```powershell
.\venv\Scripts\python.exe app.py
```

La documentación interactiva de FastAPI está en
`http://127.0.0.1:8000/docs`; el estado básico y la configuración declarada se
pueden consultar en `http://127.0.0.1:8000/health`. El endpoint de salud no
expone los valores de las variables ni garantiza que las bases de datos o
Ollama estén disponibles.

Si el cliente debe conectarse a una API en otra dirección, configura
`PIXORA_API_URL` en el entorno del proceso Flet. Para una API remota, usa HTTPS
y no pongas credenciales de base de datos en el entorno del cliente.

## Pruebas

Ejecuta la suite desde la raíz del proyecto:

```powershell
.\venv\Scripts\python.exe -m pytest
```

Las pruebas automatizadas usan dobles de prueba para servicios externos cuando
corresponde; para validar el funcionamiento integrado también se necesitan
PostgreSQL, MongoDB y, para recomendaciones reales, Ollama o Gemini.

## API principal

La mayoría de las rutas de usuario requieren un JWT. Después de iniciar sesión,
envía el token como `Authorization: Bearer <token>`.

| Método | Ruta | Descripción |
| --- | --- | --- |
| `GET` | `/health` | Estado y presencia de configuración necesaria. |
| `POST` | `/api/v1/auth/register` | Registra una cuenta y devuelve una sesión. |
| `POST` | `/api/v1/auth/login` | Inicia sesión con usuario o correo. |
| `GET` | `/api/v1/profile` | Devuelve el perfil autenticado. |
| `GET` | `/api/v1/posts` | Consulta publicaciones y estado de likes. |
| `POST` | `/api/v1/posts/{post_id}/like` | Alterna el like del usuario actual. |
| `DELETE` | `/api/v1/posts/{post_id}` | Elimina una publicación propia. |
| `POST` | `/api/v1/ai/ask` | Solicita recomendaciones estructuradas. |
| `GET` | `/docs` | Documentación Swagger interactiva. |

La API también ofrece rutas para tipos de sesión, ubicaciones, publicaciones y
medios; el esquema completo y los parámetros se pueden consultar en `/docs`.

## Datos y persistencia

- Las contraseñas se almacenan usando scrypt; no se guardan en texto plano.
- PostgreSQL conserva cuentas, publicaciones, ubicaciones y relaciones
  relacionales. El backend utiliza un pool de conexiones creado bajo demanda.
- MongoDB conserva fotos en `CONTENEDORES_FOTOGRAFÍAS`, detalles y likes en
  `DETALLES_PUBLICACIONES` y comentarios en `COMENTARIOS_COMUNIDAD`.
- Las fotos se guardan como URI de datos Base64; el tamaño admitido por
  publicación está limitado para respetar el límite BSON de MongoDB.
- Las sugerencias de respaldo de IA no se insertan como datos de usuario.
- La eliminación de una publicación valida que el JWT pertenezca a su autor y
  elimina los datos asociados.

## Solución de problemas

- **La API informa que falta configuración:** revisa que `.env` esté en la raíz
  y que las variables requeridas estén completas; reinicia Uvicorn tras editarlo.
- **Error de conexión a PostgreSQL:** revisa `POSTGRES_DSN`, conectividad,
  permisos y que el esquema esperado exista.
- **Error de MongoDB o colecciones:** valida `MONGODB_URI`, acceso de red,
  permisos y los nombres de colecciones en `pixora_db`.
- **Ollama no responde:** inicia Ollama, confirma la URL y ejecuta
  `ollama pull qwen2.5:3b` (o descarga el modelo que figure en `OLLAMA_MODEL`).
- **Gemini devuelve un error:** confirma `AI_PROVIDER=gemini`, la clave y que el
  modelo configurado esté habilitado para esa clave.
- **El cliente no conecta con la API:** comprueba que Uvicorn siga activo y que
  `PIXORA_API_URL` señale al host correcto.
- **No se puede iniciar sesión:** comprueba que PostgreSQL tenga la cuenta y que
  `PIXORA_AUTH_SECRET` no haya cambiado desde que se emitió el token.

## Entrega y manejo seguro de credenciales

Antes de subir el proyecto, confirma que `.env` no esté incluido. El repositorio
debe contener `.env.example`, que muestra los nombres y formatos de las
variables sin secretos reales. Nunca subas claves de Gemini, contraseñas,
tokens JWT, archivos de respaldo con datos personales o URI que incluyan
credenciales.

Para que el profesor pueda ejecutar el proyecto:

1. Comparte el código y `.env.example`.
2. Facilita por separado, de manera privada, acceso a servicios de prueba ya
   preparados o instrucciones para que use sus propias bases.
3. Si le entregas valores de configuración, hazlo por un canal privado y con
   credenciales de prueba de alcance limitado; no los pegues en este README,
   en commits, issues, capturas ni archivos públicos.
4. Recomienda generar un `PIXORA_AUTH_SECRET` propio y reemplazar cualquier
   credencial temporal al terminar la revisión.

<div align="center">

<img src="https://github.com/user-attachments/assets/4602601c-e3ed-4c0d-b847-24fa5a05d5d6" alt="Elevideo Banner" width="30%" />

**Plataforma inteligente de procesamiento de video**  
Convierte videos horizontales a formato vertical 9:16 con detección de rostros, reencuadre inteligente y múltiples modos de procesamiento para TikTok, Instagram Reels y YouTube Shorts.

[![Frontend](https://img.shields.io/badge/Frontend-Vercel-black?style=for-the-badge&logo=vercel)](https://elevideo.vercel.app)
[![Backend](https://img.shields.io/badge/Backend%20API-Render-46E3B7?style=for-the-badge&logo=render)](https://elevideo-ec.onrender.com/swagger-ui/index.html)
[![Java](https://img.shields.io/badge/Java-17-ED8B00?style=for-the-badge&logo=openjdk)](https://openjdk.org/)
[![Spring Boot](https://img.shields.io/badge/Spring%20Boot-3.5.11-6DB33F?style=for-the-badge&logo=springboot)](https://spring.io/projects/spring-boot)
[![React](https://img.shields.io/badge/React-JS-61DAFB?style=for-the-badge&logo=react)](https://react.dev/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python)](https://www.python.org/)

</div>

---

## 📋 Tabla de contenidos

- [¿Qué es Elevideo?](#-qué-es-elevideo)
- [Arquitectura del sistema](#-arquitectura-del-sistema)
- [Demos y deploys](#-demos-y-deploys)
- [Estructura del repositorio](#-estructura-del-repositorio)
- [Stack tecnológico](#-stack-tecnológico)
- [Evolución y autoría](#-evolución-y-autoría)
- [Equipo original](#-equipo-original)

---

## 🎬 ¿Qué es Elevideo?

Elevideo es una plataforma web que permite a creadores de contenido transformar sus videos horizontales en clips verticales listos para publicar en redes sociales, sin necesidad de editar manualmente.

El sistema detecta automáticamente los rostros en el video, calcula el encuadre óptimo en cada fotograma y aplica estabilización para generar un resultado fluido y adaptado a formatos verticales.

### Funcionalidades principales

- 📁 **Proyectos** — Organiza videos en proyectos independientes
- ⬆️ **Subida de videos** — Almacenamiento en Cloudinary con metadatos
- 🎯 **Tres modos de procesamiento:**
  - `vertical` — Convierte el video completo a 9:16
  - `short_auto` — Selecciona automáticamente un segmento
  - `short_manual` — Permite elegir inicio y duración
- 📊 **Seguimiento de jobs** — Consulta de estado y progreso del procesamiento
- 🎨 **Fondos personalizables** — Smart crop, fondo difuminado o fondo negro
- 📥 **Galería de resultados** — Renditions con preview y URLs de descarga
- 🔔 **Notificaciones por email** — Avisos cuando termina el procesamiento
- 🌗 **Interfaz light/dark** — Experiencia responsive con estados de carga, error y demo

---

## 🏗 Arquitectura del sistema

Elevideo está compuesto por tres aplicaciones que colaboran entre sí:

```text
┌─────────────────────────────────────────────────────────┐
│                     Usuario / Browser                   │
└───────────────────────────┬─────────────────────────────┘
                            │ HTTPS
                            ▼
┌─────────────────────────────────────────────────────────┐
│              Frontend (React + Tailwind CSS)            │
│                   elevideo.vercel.app                   │
└───────────────────────────┬─────────────────────────────┘
                            │ REST API + JWT
                            ▼
┌─────────────────────────────────────────────────────────┐
│           Backend Spring Boot (monolito modular)        │
│             elevideo-ec.onrender.com                    │
│                                                         │
│   auth │ user │ project │ video │ processing │ notif.   │
└──────────────┬───────────────────────┬──────────────────┘
               │ HTTP + JWT delegado   │ Webhooks
               │                       │ X-Service-Key
               ▼                       │
┌──────────────────────────┐           │
│   Procesador Python      │───────────┘
│ FastAPI + MediaPipe      │
│ OpenCV + FFmpeg          │
│     (solo local)         │
└──────────────────────────┘
```

### Flujo de procesamiento

1. El usuario sube un video desde el frontend y el archivo se almacena en **Cloudinary**.
2. El usuario crea un job de procesamiento y **Spring Boot** registra el job.
3. Spring Boot llama al servicio Python mediante un **JWT delegado de corta duración**.
4. **Python** descarga el video, procesa detección/reencuadre y ejecuta FFmpeg.
5. El resultado se vuelve a almacenar en Cloudinary.
6. Python notifica el estado y progreso al backend mediante endpoints internos protegidos.
7. Spring Boot persiste el resultado y el usuario puede visualizarlo desde la aplicación.

La comunicación usuario → backend y backend → procesador usan límites de confianza distintos: el frontend consume la API autenticada con JWT de usuario, mientras que la comunicación entre servicios utiliza credenciales y tokens específicos para servicio.

---

## 🌐 Demos y deploys

| Servicio | URL | Estado |
|---|---|---|
| 🎨 Frontend | [elevideo.vercel.app](https://elevideo.vercel.app) | ✅ Desplegado |
| ⚙️ Backend API (Swagger) | [elevideo-ec.onrender.com/swagger-ui/index.html](https://elevideo-ec.onrender.com/swagger-ui/index.html) | ✅ Desplegado |
| 🐍 Procesador Python | — | ⚠️ Ejecución local |

### Acceso demo

El login incluye un botón **Entrar a la demostración** que utiliza una cuenta verificada con proyectos, videos y resultados preparados.

- Correo: `demo@elevideo.app`
- Contraseña: `Demo123!`

Los datos de la cuenta demo se restablecen periódicamente para mantener una experiencia de revisión consistente.

> **¿Por qué el procesador Python no está desplegado?**  
> MediaPipe, OpenCV y FFmpeg realizan trabajo intensivo de CPU y memoria. La versión pública mantiene desplegados el frontend y la API, mientras que el worker de procesamiento se ejecuta localmente por restricciones de recursos del hosting utilizado. La cuenta demo incluye resultados preparados para que la experiencia principal pueda revisarse sin depender del worker.

---

## 📦 Estructura del repositorio

```text
elevideo/
├── backend/             ← API REST Spring Boot y monolito modular
├── Frontend/            ← Aplicación React desplegada en Vercel
├── elevideo-processor/  ← Procesador Python con FastAPI, MediaPipe y FFmpeg
└── Documentacion del proyecto/
```

Cada aplicación mantiene documentación propia:

- 📖 [README — Backend](./backend/README.md)
- 📖 [README — Frontend](./Frontend/README.md)
- 📖 [README — Procesador Python](./elevideo-processor/README.md)

---

## 🛠 Stack tecnológico

### Backend — Spring Boot

| Tecnología | Versión | Uso |
|---|---|---|
| Java | 17 | Lenguaje principal |
| Spring Boot | 3.5.11 | Framework REST |
| Spring Modulith | 2.0.3 | Organización como monolito modular |
| Spring Security + JJWT | 0.12.5 | Autenticación y autorización JWT |
| PostgreSQL | — | Base de datos relacional |
| Spring Data JPA | — | Persistencia |
| MapStruct | 1.6.3 | Mapeo de objetos |
| Cloudinary SDK | 1.39.0 | Almacenamiento de video |
| Thymeleaf + Resend | — | Emails transaccionales |
| SpringDoc OpenAPI | 2.8.15 | Documentación Swagger/OpenAPI |

### Frontend — React

| Tecnología | Uso |
|---|---|
| React.js (JavaScript ES6+) | Interfaz de usuario |
| React Query | Estado asíncrono y consumo de API |
| React Hook Form + Zod | Formularios y validación |
| Tailwind CSS | Sistema visual y responsive design |
| shadcn/ui / Radix | Componentes de interfaz |
| CRACO | Configuración de build |

### Procesador — FastAPI

| Tecnología | Uso |
|---|---|
| Python 3.11+ | Lenguaje principal |
| FastAPI | API del procesador |
| MediaPipe | Detección de rostros |
| OpenCV | Procesamiento de fotogramas |
| FFmpeg | Encoding, renderizado y filtros |
| NumPy | Cálculos de procesamiento |
| Cloudinary SDK | Almacenamiento de resultados |

---

## 🔄 Evolución y autoría

Elevideo **nació como un proyecto colaborativo** dentro de una simulación laboral de [No Country](https://www.nocountry.tech/). Durante esa etapa, **Edgar Ulises Camberos Arreola participó como Backend Developer** junto con el resto del equipo acreditado en la sección siguiente.

Después de finalizar la simulación, Edgar continuó la evolución de este repositorio de forma independiente. La **versión actual** incluye trabajo posterior de mantenimiento, rediseño y refactorización realizado por él, entre lo que destaca:

- refactorización del backend hacia una estructura de **monolito modular** por dominios;
- fortalecimiento de autenticación/autorización con Spring Security y JWT;
- autenticación **service-to-service** entre Spring Boot y el procesador Python;
- protección de webhooks/endpoints internos y validación de ownership;
- evolución del pipeline de procesamiento, estados de jobs, guardrails y manejo de errores;
- integración de la experiencia demo y datos preparados para revisión de portafolio;
- **rediseño e implementación de la interfaz frontend actual**, incluyendo dashboard, proyectos, videos, resultados, responsive design y temas claro/oscuro;
- mantenimiento de los deployments actuales de frontend y backend.

Esta distinción busca conservar los créditos del equipo original y, al mismo tiempo, dejar claro que el estado actual del proyecto contiene una evolución sustancial posterior a aquella entrega colaborativa.

### Para revisión técnica

Si estás revisando este repositorio como parte de un proceso de selección, algunos puntos representativos son:

- `backend/src/main/java/com/elevideo/backend/shared/security/` — seguridad JWT y autenticación de servicios
- `backend/src/main/java/com/elevideo/backend/processing/` — ciclo de vida de jobs e integración con Python
- `backend/src/main/java/com/elevideo/backend/project/` — ejemplo de módulo de dominio
- `elevideo-processor/core/auth.py` — validación del JWT delegado
- `elevideo-processor/processing/` — detección, framing, estabilización y renderizado
- `elevideo-processor/utils/processing_guardrails.py` — límites de concurrencia y antiabuso
- `Frontend/src/pages/` — flujos principales de la experiencia web actual

---

## 👥 Equipo original

Equipo de la etapa inicial desarrollada durante la simulación de No Country:

| Rol original | Nombre | LinkedIn | GitHub |
| --- | ------ | -------- | ------ |
| 📋 **Project Manager** | David H. Caycedo Blum | [![LinkedIn](https://img.shields.io/badge/LinkedIn-0A66C2?style=flat&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/davidcoachdev) | [![GitHub](https://img.shields.io/badge/GitHub-181717?style=flat&logo=github&logoColor=white)](https://github.com/davidcoachdev) |
| 🎨 **Frontend Developer** | Jhorman Nieto | [![LinkedIn](https://img.shields.io/badge/LinkedIn-0A66C2?style=flat&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/jhormandev) | [![GitHub](https://img.shields.io/badge/GitHub-181717?style=flat&logo=github&logoColor=white)](https://github.com/jhorman9) |
| 🔧 **Backend Developer** | Edgar Ulises Camberos Arreola | [![LinkedIn](https://img.shields.io/badge/LinkedIn-0A66C2?style=flat&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/edgar-camberos-8a66052bb) | [![GitHub](https://img.shields.io/badge/GitHub-181717?style=flat&logo=github&logoColor=white)](https://github.com/EdgarCamberos1894) |
| 🔧 **Backend Developer** | Eduin Pino | [![LinkedIn](https://img.shields.io/badge/LinkedIn-0A66C2?style=flat&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/eduin-pino-249b45255) | [![GitHub](https://img.shields.io/badge/GitHub-181717?style=flat&logo=github&logoColor=white)](https://github.com/Ed-Pino) |
| 🔧 **Backend Developer** | Lisandro Sánchez Morales | [![LinkedIn](https://img.shields.io/badge/LinkedIn-0A66C2?style=flat&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/polyglis-san-49914b343) | [![GitHub](https://img.shields.io/badge/GitHub-181717?style=flat&logo=github&logoColor=white)](https://github.com/polyglisdev) |

---

<div align="center">
  <sub>Origen colaborativo en No Country · evolución y mantenimiento actual: Edgar Ulises Camberos Arreola</sub>
</div>

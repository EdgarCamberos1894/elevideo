# EleVideo Frontend

Interfaz web de **EleVideo**, desarrollada en React con JavaScript, Tailwind CSS y componentes basados en Radix/shadcn. La versión actual forma parte de la evolución posterior del proyecto y está integrada con la API Spring Boot desplegada.

> El origen colaborativo del proyecto y la autoría de la evolución actual están documentados en el [README principal](../README.md).

## Tecnologías principales

- **React.js** — interfaz de usuario
- **JavaScript (ES6+)** — lenguaje principal
- **React Query** — estado asíncrono y consumo de API
- **React Hook Form + Zod** — formularios y validación
- **Tailwind CSS** — estilos y responsive design
- **Radix / shadcn/ui** — primitives y componentes de interfaz
- **CRACO** — configuración de build sin eject
- **PostCSS** — procesamiento de CSS

## Instalación

```bash
git clone https://github.com/EdgarCamberos1894/elevideo.git
cd elevideo/Frontend
npm install
```

## Scripts disponibles

Levantar el servidor de desarrollo:

```bash
npm start
```

Construir para producción:

```bash
npm run build
```

## Estructura principal

```text
Frontend/
├── public/
├── src/
│   ├── api/          # Clientes y llamadas a la API
│   ├── components/   # Componentes reutilizables
│   ├── context/      # Auth y theme context
│   ├── hooks/        # Hooks compartidos
│   ├── lib/          # Utilidades internas
│   ├── pages/        # Flujos principales de la aplicación
│   ├── App.js
│   └── index.js
├── tailwind.config.js
├── postcss.config.js
├── craco.config.js
├── package.json
└── vercel.json
```

## Despliegue

Vercel despliega el frontend integrado desde la rama `refactor-code`.

Demo pública: [https://elevideo.vercel.app](https://elevideo.vercel.app)

La pantalla de login incluye acceso directo a una cuenta demo con datos preparados para revisión del proyecto.

## Licencia

Este proyecto se encuentra bajo la licencia **MIT**.

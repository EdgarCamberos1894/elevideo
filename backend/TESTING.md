# Pruebas automatizadas del backend

La suite `WebhookHandlerServiceUnitTest` verifica reglas de procesamiento sin
arrancar Spring, conectar PostgreSQL ni llamar al microservicio Python:

- Los estados terminales (`COMPLETED`, `FAILED`, `CANCELLED`) no se alteran con
  un webhook de progreso recibido fuera de orden.
- Un trabajo activo actualiza progreso, fase, ETA y estado.
- Los trabajos inexistentes no producen escrituras.
- Una finalización exitosa guarda la versión del video y emite el evento de dominio.
- Un fallo de procesamiento no emite un evento de éxito.

Desde `backend/`:

```bash
bash ./mvnw -B -ntp '-Dtest=*UnitTest' test
```

GitHub Actions ejecuta la misma suite en los PRs dirigidos a `refactor-code`,
la rama vinculada al despliegue público de EleVideo.

`ElevideoBackendApplicationTests` es una prueba de integración de contexto
Spring (`@SpringBootTest`) y requiere configuración de infraestructura real
(PostgreSQL, secretos y servicios). No forma parte de esta suite aislada.

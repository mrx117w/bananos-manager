BANANOS MANAGER V3.4 - DOCKER LOCAL

Esta etapa mantiene SQLite. No migra PostgreSQL todavía.
La aplicación corre en un solo contenedor y la base SQLite queda persistida en un volumen Docker independiente.
Puerto: 8001

ARRANCAR:
  docker compose up -d --build

VER ESTADO:
  docker compose ps

VER LOGS:
  docker compose logs -f bananos-manager

DETENER SIN BORRAR DATOS:
  docker compose down

REINICIAR:
  docker compose restart bananos-manager

IMPORTANTE:
  NO ejecutar `docker compose down -v` salvo que se quiera eliminar también la base y uploads persistentes.

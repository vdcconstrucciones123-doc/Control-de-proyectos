# Site Audit Pro Lite

Aplicación Django para generar reportes fotográficos de obra desde celular o escritorio. La interfaz permite crear proyectos, generar reportes, organizar frentes, registrar issues con fotos y exportar un PDF desde la vista previa.

## Acceso por usuario

- `acceso/`: inicio de sesión
- `registro/`: creación de usuario
- `salir/`: cierre de sesión

La app ahora exige autenticación para entrar al panel principal.

Por esta fase, cada usuario trabaja con su propio espacio desde el navegador usando almacenamiento local separado por cuenta. Esto permite ordenar el acceso sin romper el flujo actual.

El trabajo compartido real por proyecto entre varios usuarios se implementará en la siguiente etapa con modelos y permisos en base de datos.

## Proyectos con propietario y compartición

La app ahora registra proyectos en base de datos con:

- propietario del proyecto
- miembros invitados por usuario
- roles `viewer`, `editor` y `admin`

Endpoints internos usados por la interfaz:

- `GET/POST /api/projects/`
- `PATCH/DELETE /api/projects/<slug>/`
- `POST /api/projects/<slug>/members/`

Alcance actual:

- la lista de proyectos ya es compartible entre usuarios
- los permisos de editar y compartir se controlan por rol
- el contenido detallado del reporte y su PDF siguen guardándose localmente para no romper el flujo actual

Antes de probar esta fase en local o en Render, ejecuta migraciones:

```bash
python manage.py migrate
```

## Stack actual

- Django
- Bootstrap 5
- JavaScript del lado del cliente
- SQLite en local
- PostgreSQL en Render mediante `DATABASE_URL`

Nota de deploy:
Si Render usa PostgreSQL, el proyecto necesita un driver PostgreSQL instalado. Este repositorio ya incluye `psycopg[binary]` en `requirements.txt` para que Django pueda abrir `DATABASE_URL` sin fallar en build o migrate.

## Ejecutar en local

1. Crear y activar un entorno virtual.
2. Instalar dependencias:

```bash
pip install -r requirements.txt
```

3. Ejecutar migraciones:

```bash
python manage.py migrate
```

4. Iniciar el servidor:

```bash
python manage.py runserver
```

5. Abrir:

```text
http://127.0.0.1:8000/
```

## Variables de entorno

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DATABASE_URL`
- `CLOUDINARY_URL` o alternativamente `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`
- `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD` para crear o actualizar un admin automático en deploy

Ejemplo local opcional:

```bash
set DJANGO_DEBUG=True
set DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
```

## Subir a GitHub

1. Inicializar git en la carpeta del proyecto si todavía no existe.
2. Hacer commit de todo menos `db.sqlite3`, `staticfiles` y el entorno virtual.
3. Crear un repositorio en GitHub y subir la rama principal.

Comandos típicos:

```bash
git init
git add .
git commit -m "Prepare Django app for Render deployment"
git branch -M main
git remote add origin <TU_REPO_GITHUB>
git push -u origin main
```

## Desplegar en Render

Este repositorio ya incluye [render.yaml](render.yaml) y [build.sh](build.sh).

Opciones:

1. Blueprint: crear el servicio en Render apuntando al repositorio y dejar que Render lea `render.yaml`.
2. Manual: crear un Web Service y usar estos comandos:

```bash
Build Command: ./build.sh
Start Command: gunicorn site_audit_report.wsgi:application
```

Si haces la configuración manual, crea además una base PostgreSQL en Render y asigna su `DATABASE_URL` al servicio web.

Para Cloudinary en Render deja configurada una de estas opciones:

1. Recomendada: una sola variable `CLOUDINARY_URL`
2. Alternativa: `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`

El proyecto ya queda listo para usar Cloudinary cuando esas variables existan. Si no están definidas, sigue usando almacenamiento local para archivos de media.

Si quieres que Render te deje creado tu usuario administrador en cada deploy, agrega además estas variables al servicio web:

```text
DJANGO_SUPERUSER_USERNAME=tu_usuario_admin
DJANGO_SUPERUSER_EMAIL=tu_correo@dominio.com
DJANGO_SUPERUSER_PASSWORD=tu_clave_segura
```

`build.sh` ejecuta `python manage.py ensure_admin_user` después de `migrate`. Si esas variables no existen, no falla el deploy: simplemente no crea nada.

## Estructura que sí usa Django

- `site_audit_report/settings.py`: configuración principal
- `report_app/views.py`: vistas Django
- `templates/`: plantillas HTML
- `static/report_app/`: CSS y JavaScript de la app real

## Nota sobre archivos estáticos antiguos

En la raíz todavía existen `index.html`, `app.js` y `styles.css` de una versión estática previa. La app activa para desarrollo y despliegue es la versión Django.


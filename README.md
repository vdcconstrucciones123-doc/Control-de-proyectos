# Site Audit Pro Lite

Aplicación Django para generar reportes fotográficos de obra desde celular o escritorio. La interfaz permite crear proyectos, generar reportes, organizar frentes, registrar issues con fotos y exportar un PDF desde la vista previa.

## Stack actual

- Django
- Bootstrap 5
- JavaScript del lado del cliente
- SQLite en local
- PostgreSQL en Render mediante `DATABASE_URL`

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

## Estructura que sí usa Django

- `site_audit_report/settings.py`: configuración principal
- `report_app/views.py`: vistas Django
- `templates/`: plantillas HTML
- `static/report_app/`: CSS y JavaScript de la app real

## Nota sobre archivos estáticos antiguos

En la raíz todavía existen `index.html`, `app.js` y `styles.css` de una versión estática previa. La app activa para desarrollo y despliegue es la versión Django.


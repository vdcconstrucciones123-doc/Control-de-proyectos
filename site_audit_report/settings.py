import os
import sys
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-dev-key-for-site-audit")
DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() == "true"

default_allowed_hosts = ["127.0.0.1", "localhost"]
render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME")
if render_hostname:
    default_allowed_hosts.append(render_hostname)

allowed_hosts_env = os.getenv("DJANGO_ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [host.strip() for host in allowed_hosts_env.split(",") if host.strip()] or default_allowed_hosts

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_bootstrap5",
    "report_app",
]

cloudinary_url = os.getenv("CLOUDINARY_URL", "").strip()
cloudinary_cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
cloudinary_api_key = os.getenv("CLOUDINARY_API_KEY", "").strip()
cloudinary_api_secret = os.getenv("CLOUDINARY_API_SECRET", "").strip()
use_cloudinary = bool(
    cloudinary_url or (cloudinary_cloud_name and cloudinary_api_key and cloudinary_api_secret)
)

if use_cloudinary:
    INSTALLED_APPS += [
        "cloudinary_storage",
        "cloudinary",
    ]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "site_audit_report.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "site_audit_report.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "es-pe"
TIME_ZONE = "America/Lima"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

if "test" in sys.argv:
    STORAGES["staticfiles"] = {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    }

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

if use_cloudinary:
    if cloudinary_url:
        os.environ.setdefault("CLOUDINARY_URL", cloudinary_url)
    else:
        CLOUDINARY_STORAGE = {
            "CLOUD_NAME": cloudinary_cloud_name,
            "API_KEY": cloudinary_api_key,
            "API_SECRET": cloudinary_api_secret,
            "SECURE": True,
        }
        CLOUDINARY_URL = (
            f"cloudinary://{cloudinary_api_key}:{cloudinary_api_secret}@{cloudinary_cloud_name}"
        )
        os.environ.setdefault("CLOUDINARY_URL", CLOUDINARY_URL)

    STORAGES["default"] = {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    }
    MEDIA_URL = "/media/"

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "True").lower() == "true"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/acceso/"
LOGIN_REDIRECT_URL = "/panel-principal/"
LOGOUT_REDIRECT_URL = "/acceso/"

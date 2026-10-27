# Odoo 19 + our custom_addons, for local development and testing.
# Not a hardened production image: see docker/README.md.
FROM python:3.12-slim-bookworm

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Build tools and headers for psycopg2 / python-ldap / lxml / Pillow, plus runtime libs.
# (wkhtmltopdf is not installed: PDF reports are not used by the appraisal module.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev libldap2-dev libsasl2-dev libxml2-dev libxslt1-dev \
        libjpeg-dev zlib1g-dev libfreetype6-dev libffi-dev libssl-dev \
        libmagic1 postgresql-client fonts-dejavu-core ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 --shell /bin/bash odoo \
    && mkdir -p /var/lib/odoo && chown odoo:odoo /var/lib/odoo

WORKDIR /opt/odoo

# Dependencies first so this layer is cached until requirements.txt changes.
COPY requirements.txt /opt/odoo/requirements.txt
RUN pip install -r requirements.txt

COPY --chown=odoo:odoo . /opt/odoo
# strip CRs in case git checked the script out with Windows line endings
RUN sed -i 's/\r$//' /opt/odoo/docker/entrypoint.sh && chmod +x /opt/odoo/docker/entrypoint.sh

USER odoo
VOLUME ["/var/lib/odoo"]
EXPOSE 8069 8072

ENTRYPOINT ["/opt/odoo/docker/entrypoint.sh"]
CMD ["serve"]

# Running the project with Docker

A local development / test stack: **Odoo 19 + PostgreSQL 17**, with our `custom_addons/` mounted
so code changes show up without rebuilding. It is *not* a hardened production setup.

## First time

```bash
cp docker/env.example .env          # then edit DB_PASSWORD (and ODOO_PORT if 8069 is taken)
docker compose build                # a few minutes the first time
docker compose --profile init run --rm init   # creates the database, installs the modules, adds demo logins
docker compose up -d                # starts Odoo
```

Open http://localhost:8069 (or your `ODOO_PORT`).

| Login | Password | Role |
|---|---|---|
| `admin` | `admin` | administrator / HR |
| `somchai` | `DEMO_PASSWORD` (default `demo1234`) | team lead of the sample Engineering team |
| `malee` | `DEMO_PASSWORD` | team member |

Change the `admin` password (and keep `.env` out of git: the repository already ignores dotfiles).

## Everyday commands

| Task | Command |
|---|---|
| Start / stop | `docker compose up -d` / `docker compose stop` |
| Logs | `docker compose logs -f odoo` |
| Run the tests (throw-away `odoo_test` DB) | `docker compose --profile test run --rm test` |
| Update our module after changing views/models | `docker compose run --rm odoo -d odoo -u tech_appraisal --stop-after-init` then `docker compose restart odoo` |
| Odoo shell | `docker compose run --rm odoo shell -d odoo` |
| psql | `docker compose exec db psql -U odoo -d odoo` |
| **Wipe everything** (database and files) | `docker compose down -v` |

Python changes need `docker compose restart odoo`; XML/view changes also need the `-u tech_appraisal` update above.

## Notes

- Data lives in the Docker volumes `db-data` (PostgreSQL) and `odoo-data` (Odoo filestore). `docker compose down` keeps them, `down -v` deletes them.
- The `init` job is for a new database only. To use another database name set `ODOO_DB` in `.env`.
- PDF reports need `wkhtmltopdf`, which is not in the image (the appraisal module does not use PDF reports).
- If you also run Odoo directly on your machine, give the container another port with `ODOO_PORT`.

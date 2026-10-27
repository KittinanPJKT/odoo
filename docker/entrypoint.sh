#!/bin/sh
# Container entrypoint.   Usage (as the compose "command"):
#   serve            run the web server on database $ODOO_DB          (default)
#   init             create/install $ODOO_DB with $ODOO_MODULES, then add the demo users
#   test             run the tech_appraisal tests in a throw-away database
#   <anything else>  passed straight to odoo-bin (e.g. "shell -d mydb")
set -e

DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-odoo}"
ODOO_DB="${ODOO_DB:-odoo}"
ODOO_MODULES="${ODOO_MODULES:-hr,tech_appraisal,project,hr_timesheet,hr_holidays}"
TEST_DB="${TEST_DB:-odoo_test}"

ODOO="python /opt/odoo/odoo-bin"
COMMON="--db_host=$DB_HOST --db_port=$DB_PORT --db_user=$DB_USER --db_password=$DB_PASSWORD \
--addons-path=/opt/odoo/addons,/opt/odoo/custom_addons --data-dir=/var/lib/odoo"

case "${1:-serve}" in
    serve)
        # shellcheck disable=SC2086
        exec $ODOO $COMMON --http-interface=0.0.0.0 -d "$ODOO_DB" --db-filter="^${ODOO_DB}\$"
        ;;
    init)
        # shellcheck disable=SC2086
        $ODOO $COMMON -d "$ODOO_DB" -i "$ODOO_MODULES" --without-demo=all --stop-after-init
        # the "shell" sub-command must come before the options
        # shellcheck disable=SC2086
        $ODOO shell $COMMON -d "$ODOO_DB" --log-level=warn < /opt/odoo/docker/demo_users.py
        ;;
    test)
        # shellcheck disable=SC2086
        exec $ODOO $COMMON -d "$TEST_DB" -i hr,tech_appraisal --without-demo=all \
            --test-enable --test-tags /tech_appraisal --stop-after-init
        ;;
    *)
        # shellcheck disable=SC2086
        exec $ODOO "$@" $COMMON
        ;;
esac

#!/bin/sh

# Save current directory
#ORIG_DIR=$(pwd)

# Use a trap to return to original directory on exit
#trap 'cd "$ORIG_DIR"' EXIT

# Copy module to be tested
cp -r delivery_ups_oca ~/Nitrokey/Odoo/initos-odoo-modules-18.0/odoo/parts/OCA/delivery-carrier/

# Change to the desired directory
#cd ~/Nitrokey/Odoo/initos-odoo-modules-15.0 || exit 1

# Execute the tests
#docker compose run --rm odoo odoo test parts/OCA/social/mail_gateway_zulip

docker compose \
--file ~/Nitrokey/Odoo/initos-odoo-modules-15.0-demodata/docker-compose.yaml \
--project-directory ~/Nitrokey/Odoo/initos-odoo-modules-15.0-demodata \
run --rm odoo \
odoo test parts/OCA/delivery-carrier/delivery_ups_oca

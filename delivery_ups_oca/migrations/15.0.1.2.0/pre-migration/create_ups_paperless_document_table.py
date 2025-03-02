# Copyright 2025 Nitrokey GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Create ups_paperless_document table if it doesn't exist."""
    _logger.info("Creating ups_paperless_document table")
    cr.execute(
        """
        CREATE TABLE IF NOT EXISTS ups_paperless_document (
            id SERIAL PRIMARY KEY,
            create_uid INTEGER,
            create_date TIMESTAMP WITHOUT TIME ZONE,
            write_uid INTEGER,
            write_date TIMESTAMP WITHOUT TIME ZONE,
            ups_paperless_file BYTEA,
            file_name VARCHAR,
            ups_document_type VARCHAR,
            ups_stock_picking_id INTEGER
        )
        """
    )

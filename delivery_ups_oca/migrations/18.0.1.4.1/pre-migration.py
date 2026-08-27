# Copyright 2025 Nitrokey GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


def migrate(cr, version):
    """Rename stock.picking.document_id -> ups_document_id.

    The field holds the UPS paperless Forms History Document ID. It is
    renamed for consistency with the other ups_* fields. The rename is only
    performed when the old column still exists and the new one does not yet,
    so the script is safe on fresh installs and idempotent on re-runs.
    """
    cr.execute(
        """
        SELECT
            EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'stock_picking'
                AND column_name = 'document_id'
            ) AS old_exists,
            EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'stock_picking'
                AND column_name = 'ups_document_id'
            ) AS new_exists
        """
    )
    old_exists, new_exists = cr.fetchone()
    if old_exists and not new_exists:
        cr.execute(
            "ALTER TABLE stock_picking " "RENAME COLUMN document_id TO ups_document_id"
        )
        cr.execute(
            """
            UPDATE ir_model_fields
            SET name = 'ups_document_id'
            WHERE name = 'document_id'
            AND model = 'stock.picking'
            """
        )

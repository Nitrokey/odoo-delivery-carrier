# Copyright 2025 Nitrokey GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


def _column_exists(cr, table, column):
    cr.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    return bool(cr.fetchone())


def migrate(cr, version):
    """Rename stock.picking.document_id -> ups_document_identifier.

    The field holds the UPS paperless Forms History Document ID. It is
    renamed for consistency with the other ups_* fields and to avoid the
    ``_id`` suffix, which is reserved for Many2one fields. The rename is
    only performed when the old column still exists and the new one does
    not yet, so the script is safe on fresh installs and idempotent on
    re-runs.
    """
    if not _column_exists(cr, "stock_picking", "document_id"):
        return
    if _column_exists(cr, "stock_picking", "ups_document_identifier"):
        return
    cr.execute(
        "ALTER TABLE stock_picking "
        "RENAME COLUMN document_id TO ups_document_identifier"
    )
    cr.execute(
        """
        UPDATE ir_model_fields
        SET name = 'ups_document_identifier'
        WHERE name = 'document_id'
        AND model = 'stock.picking'
        """
    )

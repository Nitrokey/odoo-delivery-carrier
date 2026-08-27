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
    ``_id`` suffix, which is reserved for Many2one fields. The deployed
    version stored the value in ``document_id``; an intermediate version may
    have already renamed it to ``ups_document_id``. Both source columns are
    handled here. The rename is only performed when a source column still
    exists and the target one does not yet, so the script is safe on fresh
    installs and idempotent on re-runs.
    """
    new_column = "ups_document_identifier"
    if _column_exists(cr, "stock_picking", new_column):
        return
    old_column = None
    for candidate in ("document_id", "ups_document_id"):
        if _column_exists(cr, "stock_picking", candidate):
            old_column = candidate
            break
    if not old_column:
        return
    # Column names come from a fixed whitelist, not user input.
    cr.execute(  # pylint: disable=sql-injection
        f"ALTER TABLE stock_picking RENAME COLUMN {old_column} TO {new_column}"
    )
    cr.execute(
        """
        UPDATE ir_model_fields
        SET name = %s
        WHERE name = %s
        AND model = 'stock.picking'
        """,
        (new_column, old_column),
    )

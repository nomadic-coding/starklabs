# Stock Picking: Inline Lot/Serial Numbers

View-only usability tweaks for entering lot/serial numbers on transfers in
Odoo 18. No business logic is changed.

- **Operations tab**: the *Serial Numbers* column is shown by default instead
  of being hidden in the optional columns. As in standard, it is editable for
  serial-tracked products.
- **Details popup** (the list icon on a move line): on deliveries standard
  Odoo only offers *Pick From* (location / lot / package) and hides the
  *Lot/Serial Number* column. The column is now shown next to *Pick From*, so
  a lot or serial can be typed or scanned directly.

Both are shown only to users in *Inventory / Manage Lots & Serial Numbers*.

## License

LGPL-3.0 or later. Copyright 2026 STARK LABS.

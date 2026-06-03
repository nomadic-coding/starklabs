# Copyright 2026 STARK LABS
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

{
    "name": "Payment Provider: Tilopay",
    "version": "18.0.1.0.9",
    "category": "Accounting/Payment Providers",
    "sequence": 350,
    "summary": "Accept card payments with Tilopay.",
    "author": "STARK LABS",
    "website": "https://www.starklabs.app",
    "license": "LGPL-3",
    "depends": ["payment", "sale"],
    "data": [
        "views/payment_tilopay_templates.xml",
        "views/payment_form_templates.xml",
        "views/payment_templates.xml",
        "views/payment_provider_views.xml",
        "data/payment_method_data.xml",
        "data/payment_provider_data.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "payment_tilopay/static/src/scss/backend_payment_widget.scss",
            "payment_tilopay/static/src/js/portal_payment_form.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
    "installable": True,
}

# Copyright 2026 STARK LABS
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from . import controllers
from . import models

import odoo.addons.payment as payment


def post_init_hook(env):
    payment.setup_provider(env, 'tilopay')


def uninstall_hook(env):
    payment.reset_payment_provider(env, 'tilopay')

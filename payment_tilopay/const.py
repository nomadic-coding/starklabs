# Copyright 2026 STARK LABS
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

LOGIN_URL = 'https://app.tilopay.com/api/v1/loginSdk'
SDK_URL = 'https://app.tilopay.com/sdk/v2/sdk_tpay.min.js'
RETURN_URL = '/payment/tilopay/return'
FORM_VALUES_URL = '/payment/tilopay/form_values'
LOG_ERROR_URL = '/payment/tilopay/log_error'

DEFAULT_PAYMENT_METHOD_CODES = {'tilopay', 'card'}

STATUS_DONE = frozenset({'1', 'success', 'approved'})
STATUS_CANCEL = frozenset({'0', 'failed', 'rejected', 'error', 'cancel'})

SENSITIVE_LOG_KEYS = frozenset({'token', 'password', 'key', 'access_token'})

# Required by Tilopay.Init() — see https://tilopay.com/documentacion/sdk
INIT_REQUIRED_FIELDS = frozenset({
    'billToEmail',
    'orderNumber',
})

# Fallback values when partner data is missing (SDK validate + payment API reject "").
SDK_BILLING_DEFAULTS = {
    'billToAddress2': '-',
    'billToCity': '-',
    'billToState': '-',
    'billToZipPostCode': '00000',
    'billToTelephone': '88888888',
}

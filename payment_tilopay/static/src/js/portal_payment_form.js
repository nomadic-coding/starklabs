/** @odoo-module **/
/* global Tilopay */

import { _t } from "@web/core/l10n/translation";
import { loadJS } from "@web/core/assets";
import { rpc, RPCError } from "@web/core/network/rpc";
import paymentForm from "@payment/js/payment_form";

const SDK_URL = "https://app.tilopay.com/sdk/v2/sdk_tpay.min.js";

let tilopaySdkLoadPromise = null;

function waitForTilopaySdk() {
    return new Promise((resolve, reject) => {
        if (typeof Tilopay !== "undefined") {
            resolve();
            return;
        }
        let attempts = 0;
        const timer = window.setInterval(() => {
            attempts += 1;
            if (typeof Tilopay !== "undefined") {
                window.clearInterval(timer);
                resolve();
            } else if (attempts >= 50) {
                window.clearInterval(timer);
                reject(new Error("Tilopay SDK load timeout"));
            }
        }, 100);
    });
}

/** Load Tilopay SDK once; re-injecting the script throws (duplicate baseUrlTilopay). */
async function loadTilopaySdk() {
    if (typeof Tilopay !== "undefined") {
        return;
    }
    if (!tilopaySdkLoadPromise) {
        tilopaySdkLoadPromise = loadJS(SDK_URL)
            .then(() => waitForTilopaySdk())
            .catch((error) => {
                tilopaySdkLoadPromise = null;
                throw error;
            });
    }
    return tilopaySdkLoadPromise;
}

function ensureTilopay3dsContainer() {
    document.querySelectorAll("#responseTilopay").forEach((element, index) => {
        if (index > 0) {
            element.remove();
        }
    });
    let responseEl = document.getElementById("responseTilopay");
    if (!responseEl) {
        responseEl = document.createElement("div");
        responseEl.id = "responseTilopay";
    }
    responseEl.innerHTML = "";
    responseEl.classList.remove("d-none");
    responseEl.style.display = "block";
    if (responseEl.parentElement !== document.body) {
        document.body.appendChild(responseEl);
    }
    return responseEl;
}

function isTilopayDebugMode() {
    return Boolean(typeof odoo !== "undefined" && odoo.debug);
}

function updateTilopayLoadingMessage(container) {
    const loadingBlock = container?.querySelector(".o_tilopay_loading");
    if (!loadingBlock) {
        return;
    }
    loadingBlock.classList.remove("d-none");
    const message = loadingBlock.querySelector(".o_message");
    if (message) {
        message.textContent = _t("Loading payment methods...");
    }
    const spinner = loadingBlock.querySelector(".o_spinner img");
    if (spinner) {
        spinner.alt = _t("Loading...");
    }
}

function getTilopayFormHtml() {
    const paymentMethodHiddenClass = isTilopayDebugMode() ? "" : "d-none";
    return `
    <div class="o_tilopay_portal_form">
        <div class="card shadow-sm border">
            <div class="card-body p-4">
                <div class="d-flex align-items-center gap-2 mb-1">
                    <i class="fa fa-credit-card o_tilopay_card_icon" aria-hidden="true"></i>
                    <h6 class="card-title mb-0 fw-semibold">${_t("Card details")}</h6>
                </div>
                <p class="text-muted small mb-4">${_t("Enter the card information to process this payment.")}</p>
                <div class="o_tilopay_loading d-flex flex-column align-items-center justify-content-center py-4">
                    <div class="o_spinner mb-3">
                        <img src="/web/static/img/spin.svg" alt="${_t("Loading...")}"/>
                    </div>
                    <div class="o_message text-muted small text-center px-4">${_t("Loading payment methods...")}</div>
                </div>
                <div class="payFormTilopay d-none">
                    <div class="mb-3 o_tilopay_payment_method_group ${paymentMethodHiddenClass}">
                        <label class="form-label" for="tlpy_payment_method">${_t("Payment method")}</label>
                        <select id="tlpy_payment_method" class="form-select">
                            <option value="">${_t("Select a payment method")}</option>
                        </select>
                    </div>
                    <select id="tlpy_saved_cards" class="d-none">
                        <option value=""></option>
                    </select>
                    <div class="mb-3">
                        <label class="form-label" for="tlpy_cc_number">${_t("Card number")}</label>
                        <div class="input-group">
                            <span class="input-group-text">
                                <i class="fa fa-credit-card" aria-hidden="true"></i>
                            </span>
                            <input type="text"
                                   id="tlpy_cc_number"
                                   class="form-control"
                                   maxlength="19"
                                   autocomplete="cc-number"
                                   inputmode="numeric"
                                   placeholder="${_t("1234 5678 9012 3456")}"/>
                        </div>
                    </div>
                    <div class="row g-3">
                        <div class="col-md-7">
                            <label class="form-label" for="tlpy_cc_expiration_date">${_t("Expiration")}</label>
                            <input type="text"
                                   id="tlpy_cc_expiration_date"
                                   class="form-control"
                                   maxlength="5"
                                   autocomplete="cc-exp"
                                   inputmode="numeric"
                                   placeholder="${_t("MM / YY")}"/>
                        </div>
                        <div class="col-md-5">
                            <label class="form-label" for="tlpy_cvv">${_t("Security code")}</label>
                            <div class="input-group">
                                <input type="text"
                                       id="tlpy_cvv"
                                       class="form-control"
                                       maxlength="4"
                                       autocomplete="cc-csc"
                                       inputmode="numeric"
                                       placeholder="${_t("CVV")}"/>
                                <span class="input-group-text" title="${_t("3 or 4 digits on the back of your card")}">
                                    <i class="fa fa-lock" aria-hidden="true"></i>
                                </span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>`;
}

function revealTilopayPaymentForm(container) {
    container?.closest('[name="o_payment_inline_form"]')?.classList.remove("d-none");
    container?.querySelector(".o_tilopay_loading")?.classList.add("d-none");
    container?.querySelector(".payFormTilopay")?.classList.remove("d-none");
    container?.querySelector(".o_tilopay_payment_method_group")?.classList.toggle(
        "d-none",
        !isTilopayDebugMode(),
    );
}

function findContadoMethod(methods) {
    return methods?.find((method) => method.name?.toLowerCase().includes("contado"));
}

paymentForm.include({
    tilopayState: {},

    async start() {
        await this._super(...arguments);
        const checkedRadio = this.el.querySelector('input[name="o_payment_radio"]:checked');
        if (checkedRadio && this._getProviderCode(checkedRadio) === "tilopay") {
            const paymentOptionId = this._getPaymentOptionId(checkedRadio);
            if (this.tilopayState[paymentOptionId]?.ready) {
                this._showInputs();
            } else {
                this._hideInputs();
            }
        }
    },

    async _selectPaymentOption(ev) {
        const checkedRadio = ev.target;
        if (this._getProviderCode(checkedRadio) !== "tilopay") {
            return this._super(...arguments);
        }
        this._hideInputs();
        this._disableButton();
        await this._expandInlineForm(checkedRadio);
        const paymentOptionId = this._getPaymentOptionId(checkedRadio);
        if (this.tilopayState[paymentOptionId]?.ready) {
            this._showInputs();
        }
        this._enableButton(false);
    },

    async _prepareInlineForm(providerId, providerCode, paymentOptionId, paymentMethodCode, flow) {
        if (providerCode !== "tilopay") {
            return this._super(...arguments);
        }
        if (flow === "token") {
            return;
        }

        this._setPaymentFlow("direct");

        const radio = this.el.querySelector(
            `input[name="o_payment_radio"][data-payment-option-id="${paymentOptionId}"]`
        ) || this.el.querySelector('input[name="o_payment_radio"]:checked');
        const inlineForm = radio && this._getInlineForm(radio);
        inlineForm?.classList.remove("d-none");
        const container = this._ensureTilopayContainer(inlineForm);
        if (!container) {
            this._displayErrorDialog(
                _t("Payment error"),
                _t("Tilopay form is not available. Contact your administrator."),
            );
            return;
        }

        if (this.tilopayState[paymentOptionId]?.ready) {
            revealTilopayPaymentForm(container);
            return;
        }

        this._hideInputs();
        updateTilopayLoadingMessage(container);

        this.call("ui", "block", { message: _t("Loading payment methods...") });
        try {
            await loadTilopaySdk();
            ensureTilopay3dsContainer();

            const formValues = await this._tilopayFetchPreviewFormValues(providerId);
            const initResult = await Tilopay.Init(formValues);
            if (initResult?.message !== "Success") {
                this._displayErrorDialog(
                    _t("Payment error"),
                    initResult?.message || _t("Could not initialize Tilopay."),
                );
                return;
            }

            const methods = initResult?.methods || [];
            const contadoMethod = findContadoMethod(methods);
            if (!contadoMethod) {
                this._displayErrorDialog(
                    _t("Payment error"),
                    _t("The Contado payment method is not available."),
                );
                return;
            }

            this._tilopayFillMethods(container, methods);
            const methodSelect = container.querySelector("#tlpy_payment_method");
            if (methodSelect) {
                methodSelect.value = contadoMethod.id;
            }
            await Tilopay.updateOptions({ method: contadoMethod.id });

            revealTilopayPaymentForm(container);
            this.tilopayState[paymentOptionId] = {
                container,
                ready: true,
                methodId: contadoMethod.id,
            };
            this._showInputs();
        } catch (error) {
            const message = error instanceof RPCError
                ? error.data.message
                : error.message || _t("Could not load Tilopay.");
            this._displayErrorDialog(_t("Payment error"), message);
        } finally {
            this.call("ui", "unblock");
        }
    },

    _ensureTilopayContainer(inlineForm) {
        if (!inlineForm) {
            return null;
        }
        let container = inlineForm.querySelector('[name="o_tilopay_form"]');
        if (!container) {
            container = document.createElement("div");
            container.setAttribute("name", "o_tilopay_form");
            inlineForm.insertBefore(container, inlineForm.firstChild);
        }
        if (!container.querySelector(".o_tilopay_portal_form")) {
            container.innerHTML = getTilopayFormHtml();
        }
        ensureTilopay3dsContainer();
        return container;
    },

    async _processDirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        if (providerCode !== "tilopay") {
            return this._super(...arguments);
        }

        const state = this.tilopayState[paymentOptionId];
        if (!state?.container) {
            this._displayErrorDialog(
                _t("Payment error"),
                _t("Tilopay form is not available. Refresh the page and try again."),
            );
            this._enableButton();
            return;
        }

        let formValues;
        try {
            formValues = await this._tilopayFetchFormValues(processingValues);
        } catch (error) {
            const message = error instanceof RPCError
                ? error.data.message
                : error.message || _t("Could not prepare Tilopay payment.");
            this._displayErrorDialog(_t("Payment error"), message);
            this._enableButton();
            return;
        }

        try {
            revealTilopayPaymentForm(state.container);
            ensureTilopay3dsContainer();

            const initResult = await Tilopay.Init(formValues);
            if (initResult?.message !== "Success") {
                await this._tilopayLogError(
                    processingValues.reference,
                    initResult?.message || "Init failed",
                );
                this._displayErrorDialog(
                    _t("Payment error"),
                    initResult?.message || _t("Could not initialize Tilopay."),
                );
                this._enableButton();
                return;
            }

            const prodError = this._tilopayCheckProductionRequirements(formValues, initResult);
            if (prodError) {
                await this._tilopayLogError(processingValues.reference, prodError);
                this._displayErrorDialog(_t("Payment error"), prodError);
                this._enableButton();
                return;
            }

            const methodSelect = state.container.querySelector("#tlpy_payment_method");
            const previousMethod = methodSelect?.value;
            this._tilopayFillMethods(state.container, initResult?.methods || []);
            if (previousMethod && [...methodSelect.options].some((o) => o.value === previousMethod)) {
                methodSelect.value = previousMethod;
            }
            const methodId = this._tilopayPickMethod(initResult?.methods || [], methodSelect?.value);
            if (!methodId) {
                this._displayErrorDialog(_t("Payment error"), _t("Select a payment method."));
                this._enableButton();
                return;
            }
            if (methodSelect) {
                methodSelect.value = methodId;
            }

            const encryptError = await this._tilopayEncryptCardIfNeeded(initResult);
            if (encryptError) {
                await this._tilopayLogError(processingValues.reference, encryptError);
                this._displayErrorDialog(_t("Payment error"), encryptError);
                this._enableButton();
                return;
            }

            await Tilopay.updateOptions({
                method: methodId,
                returnData: JSON.stringify({
                    reference: processingValues.reference,
                    amount: processingValues.amount,
                    currency: formValues.currency,
                }),
            });
            ensureTilopay3dsContainer();
            const response = await Tilopay.startPayment();
            if (response?.message && response.message !== "Success") {
                await this._tilopayLogError(
                    processingValues.reference,
                    response.message,
                    JSON.stringify(response),
                );
                this._displayErrorDialog(_t("Payment failed"), response.message);
                this._enableButton();
            }
        } catch (error) {
            await this._tilopayLogError(
                processingValues.reference,
                error.message || "Unknown error",
            );
            const message = error.message?.includes("submit")
                ? _t(
                    "The 3-D Secure verification could not start. "
                    + "Refresh the page and try again."
                )
                : (error.message || _t("Unknown error"));
            this._displayErrorDialog(_t("Payment failed"), message);
            this._enableButton();
        }
    },

    _tilopayCheckProductionRequirements(formValues, initResult) {
        if (initResult?.environment !== "PROD") {
            return null;
        }
        const redirect = formValues.redirect || "";
        if (redirect.includes("localhost") || redirect.includes("127.0.0.1")) {
            return _t(
                "Tilopay production requires a public HTTPS return URL. "
                + "Set web.base.url or configure Return URL on the Tilopay payment provider."
            );
        }
        return null;
    },

    _tilopayPickMethod(methods, selectedValue) {
        if (selectedValue) {
            return selectedValue;
        }
        const contadoMethod = findContadoMethod(methods);
        if (contadoMethod) {
            return contadoMethod.id;
        }
        const cardMethod = methods.find((method) => method.type === "card");
        return (cardMethod || methods[0])?.id || "";
    },

    async _tilopayFetchPreviewFormValues(providerId) {
        const saleOrderId = new URLSearchParams(window.location.search).get("sale_order_id")
            || window.location.pathname.match(/\/my\/orders\/(\d+)/)?.[1];
        return rpc("/payment/tilopay/form_values", {
            provider_id: providerId,
            partner_id: parseInt(this.paymentContext.partnerId),
            amount: parseFloat(this.paymentContext.amount),
            currency_id: parseInt(this.paymentContext.currencyId),
            access_token: this.paymentContext.accessToken,
            sale_order_id: saleOrderId ? parseInt(saleOrderId) : null,
            is_validation: this.paymentContext.mode === "validation",
        });
    },

    async _tilopayFetchFormValues(processingValues) {
        const saleOrderId = new URLSearchParams(window.location.search).get("sale_order_id")
            || window.location.pathname.match(/\/my\/orders\/(\d+)/)?.[1];
        return rpc("/payment/tilopay/form_values", {
            provider_id: processingValues.provider_id,
            partner_id: processingValues.partner_id,
            amount: processingValues.amount,
            currency_id: processingValues.currency_id,
            access_token: this.paymentContext.accessToken,
            sale_order_id: saleOrderId ? parseInt(saleOrderId) : null,
            transaction_reference: processingValues.reference,
            is_validation: this.paymentContext.mode === "validation",
        });
    },

    async _tilopayEncryptCardIfNeeded(initResult) {
        if (initResult?.environment !== "PROD") {
            return null;
        }
        if (typeof Tilopay.TxEncrypt === "function") {
            await Tilopay.TxEncrypt();
        }
        if (typeof Tilopay.TxEncryptCVV === "function") {
            await Tilopay.TxEncryptCVV();
        }
        if (typeof Tilopay.getCipherData === "function") {
            const cipher = await Tilopay.getCipherData();
            if (!cipher?.card || !cipher?.cvv) {
                return _t(
                    "Card encryption failed. Check your card details and try again."
                );
            }
        }
        return null;
    },

    async _tilopayLogError(reference, message, details) {
        try {
            await rpc("/payment/tilopay/log_error", { reference, message, details });
        } catch {
            // Best-effort logging only.
        }
    },

    _tilopayFillMethods(container, methods) {
        const select = container.querySelector("#tlpy_payment_method");
        if (!select) {
            return;
        }
        while (select.options.length > 1) {
            select.remove(1);
        }
        for (const method of methods) {
            const option = document.createElement("option");
            option.value = method.id;
            option.textContent = method.name;
            select.appendChild(option);
        }
    },
});

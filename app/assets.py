"""Controller for the portfolio: holdings, live prices, buying and selling.

Price lookups run in a separate process started by the asset service, so the
market-data libraries are never loaded into the interface process. Their
results arrive on a worker thread and are handed to the interface thread
through `run_on_main_thread`.
"""

from __future__ import annotations

from PySide6.QtCore import Property, Signal, Slot

from app.accounts import FormError, _Mutating, read_amount
from app.controllers import display_title, format_amount, short_date
from services.background_task_manager import BackgroundTaskManager
from app.language import later, say, tr
from utils.logging_config import get_logger
from utils.ui_dispatch import run_on_main_thread

ASSET_TYPES = ("Hisse", "Altın", "Döviz", "Kripto", "Tahvil", "Diğer")
GOLD_KINDS = (
    ("GC=F", "Gram Altın", later("Gram gold")),
    ("GOLD-CEYREK", "Çeyrek Altın", later("Quarter gold coin")),
    ("GOLD-YARIM", "Yarım Altın", later("Half gold coin")),
    ("GOLD-TAM", "Tam Altın", later("Full gold coin")),
    ("GOLD-ONS", "Ons Altın", later("Ounce of gold")),
)
_GOLD_NAMES = {stored: label for _code, stored, label in GOLD_KINDS}


def gold_name(stored: str) -> str:
    """A gold holding's stored kind as shown; any other name is the user's own."""
    label = _GOLD_NAMES.get(stored)
    return say(label) if label else stored
_CODE_HINTS = {
    "Hisse": "THYAO", "Döviz": "USD", "Kripto": "BTC", "Tahvil": later("Symbol"), "Diğer": later("Symbol"),
}


def read_quantity(text: str) -> float:
    """'1.250,5' or '0.00012' -> a positive float. A comma is always decimal."""
    cleaned = (text or "").strip().replace(" ", "")
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        value = float(cleaned)
    except ValueError:
        raise FormError(say("Enter a valid quantity, for example 2 or 0,5.")) from None
    if not 0 < value < 1e12:
        raise FormError(say("The quantity must be greater than 0."))
    return value


def format_quantity(value: float) -> str:
    text = f"{value:,.8f}".rstrip("0").rstrip(".")
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def format_signed_amount(value: float) -> str:
    return ("−" if value < 0 else "+") + format_amount(value) + " ₺"


class AssetsController(_Mutating):
    changed = Signal()
    pricingChanged = Signal()
    quoteChanged = Signal()

    def __init__(self, tasks: BackgroundTaskManager, parent=None):
        super().__init__(tasks, parent)
        self._holdings: list[dict] = []
        self._history: list[dict] = []
        self._totals = {"value": "—", "cost": "—", "pnl": "", "direction": 0}
        self._pricing = False
        self._unpriced = 0
        self._generation = 0
        self._quote = ""
        self._quote_busy = False
        self._quote_generation = 0
        self.dataChanged.connect(self.refresh)

    # -- state ---------------------------------------------------------------
    @Property("QVariantList", notify=changed)
    def holdings(self):
        return self._holdings

    @Property("QVariantList", notify=changed)
    def history(self):
        return self._history

    @Property(str, notify=changed)
    def valueText(self):
        return self._totals["value"]

    @Property(str, notify=changed)
    def costText(self):
        return self._totals["cost"]

    @Property(str, notify=changed)
    def pnlText(self):
        return self._totals["pnl"]

    @Property(int, notify=changed)
    def pnlDirection(self):
        return self._totals["direction"]

    @Property(int, notify=changed)
    def unpricedCount(self):
        """Holdings whose current price could not be fetched."""
        return self._unpriced

    @Property(bool, notify=pricingChanged)
    def pricing(self):
        return self._pricing

    @Property("QVariantList", constant=True)
    def types(self):
        return [{"key": key, "label": tr(key)} for key in ASSET_TYPES]

    @Property("QVariantList", constant=True)
    def goldKinds(self):
        return [{"key": code, "label": say(label)} for code, _stored, label in GOLD_KINDS]

    @Slot(str, result=str)
    def codeHint(self, asset_type):
        return say(_CODE_HINTS.get(asset_type, "Symbol"))

    @Property(str, notify=quoteChanged)
    def quote(self):
        """The last looked-up unit price as form text, or ''."""
        return self._quote

    @Property(bool, notify=quoteChanged)
    def quoteBusy(self):
        return self._quote_busy

    # -- loading -------------------------------------------------------------
    @Slot()
    def refresh(self):
        self._load(force=False)

    @Slot()
    def refreshPrices(self):
        self._load(force=True)

    def _load(self, force: bool) -> None:
        self._generation += 1
        generation = self._generation

        def fetch():
            from database.db import get_all_assets, get_asset_transaction_history
            from services.price_service import enrich_assets_from_cache

            assets = get_all_assets()
            return assets, enrich_assets_from_cache(assets), get_asset_transaction_history(20)

        def loaded(data):
            if generation != self._generation:
                return
            assets, cached, history = data
            self._history = [self._history_row(item) for item in history]
            self._show(cached if cached else assets)
            if assets:
                self._price(assets, generation, force)

        def failed(error):
            get_logger().exception(
                "Varlıklar yüklenemedi.",
                exc_info=(type(error), error, error.__traceback__),
            )
            self._set_message(say("Your assets could not be loaded."))

        self._tasks.submit(
            "assets", lambda _cancel: fetch(),
            on_success=loaded, on_error=failed, replace=True,
        )

    def _price(self, assets: list[dict], generation: int, force: bool) -> None:
        from services.asset_service import fetch_portfolio_with_prices

        self._pricing = True
        self.pricingChanged.emit()

        def deliver(enriched, final):
            def apply():
                if generation != self._generation:
                    return
                if enriched:
                    self._show(enriched)
                if final:
                    self._pricing = False
                    self.pricingChanged.emit()
            run_on_main_thread(apply)

        fetch_portfolio_with_prices(
            assets,
            lambda enriched: deliver(enriched, True),
            cache_callback=lambda enriched: deliver(enriched, False),
            force_refresh=force,
        )

    def _show(self, assets: list[dict]) -> None:
        views = []
        value = cost = 0.0
        unpriced = 0
        for asset in assets:
            quantity = float(asset["quantity"])
            unit_cost = float(asset["purchase_price"])
            asset_cost = unit_cost * quantity
            price = asset.get("current_price")
            priced = price is not None
            asset_value = asset.get("total_value") if priced else None
            if asset_value is None and priced:
                asset_value = float(price) * quantity
            pnl = asset.get("pnl_amount") if priced else None
            if pnl is None and priced:
                pnl = asset_value - asset_cost
            pct = asset.get("pnl_pct") if priced else None
            cost += asset_cost
            if priced:
                value += asset_value
            else:
                value += asset_cost
                unpriced += 1
            views.append({
                "id": asset["id"],
                "name": gold_name(asset["asset_name"]),
                "code": asset["asset_code"],
                "kind": tr(asset["asset_type"]),
                "quantityText": format_quantity(quantity),
                "quantity": quantity,
                "costText": f"{format_amount(unit_cost)} ₺",
                "priceText": f"{format_amount(price)} ₺" if priced else "—",
                "priceForm": format_amount(price) if priced else "",
                "valueText": f"{format_amount(asset_value)} ₺" if priced else "—",
                "pnlText": (
                    format_signed_amount(pnl)
                    + (f"  ·  {'−' if pct < 0 else '+'}{abs(pct):.1f} %".replace(".", ",")
                       if pct is not None else "")
                ) if priced else say("No price"),
                "direction": ((pnl > 0) - (pnl < 0)) if priced else 0,
                "priced": priced,
            })
        total_pnl = value - cost
        self._holdings = views
        self._unpriced = unpriced
        self._totals = {
            "value": f"{format_amount(value)} ₺",
            "cost": f"{format_amount(cost)} ₺",
            "pnl": (
                format_signed_amount(total_pnl)
                + (f"  ·  {'−' if total_pnl < 0 else '+'}"
                   f"{abs(total_pnl / cost * 100):.1f} %".replace(".", ",") if cost else "")
            ) if views else "",
            "direction": (total_pnl > 0) - (total_pnl < 0),
        }
        self.changed.emit()

    @staticmethod
    def _history_row(item: dict) -> dict:
        income = item["type"] == "income"
        return {
            "date": short_date(item["date"]) if item["date"] else "",
            "title": display_title(item["description"] or item["category"]),
            "kind": tr(item["category"]),
            "amount": ("+" if income else "−") + format_amount(item["amount"]) + " ₺",
            "income": income,
        }

    # -- quote ---------------------------------------------------------------
    @Slot(str, str)
    def lookUp(self, asset_type, code):
        """Fetches the current unit price for the add dialog."""
        from services.asset_service import fetch_portfolio_with_prices

        code = (code or "").strip().upper()
        if not code:
            self._set_message(say("Enter a symbol first."))
            return
        self._quote_generation += 1
        generation = self._quote_generation
        self._quote, self._quote_busy = "", True
        self.quoteChanged.emit()
        self._set_message("")

        def deliver(enriched):
            def apply():
                if generation != self._quote_generation:
                    return
                price = enriched[0].get("current_price") if enriched else None
                self._quote_busy = False
                self._quote = format_amount(price) if price else ""
                self.quoteChanged.emit()
                if not price:
                    self._set_message(
                        say("No price was found for this symbol. You can still enter one yourself.")
                    )
            run_on_main_thread(apply)

        probe = [{
            "id": 0, "asset_name": code, "asset_code": code, "asset_type": asset_type,
            "purchase_price": 1.0, "quantity": 1.0,
        }]
        fetch_portfolio_with_prices(probe, deliver, force_refresh=True)

    @Slot()
    def clearQuote(self):
        self._quote_generation += 1
        self._quote, self._quote_busy = "", False
        self.quoteChanged.emit()

    # -- actions -------------------------------------------------------------
    @Slot(str, str, str, str, str, int, bool)
    def buy(self, asset_type, code, name, quantity_text, price_text, account_id, deduct):
        def work():
            from services.asset_purchase_service import AssetPurchaseService

            symbol = (code or "").strip().upper()
            if asset_type not in ASSET_TYPES:
                raise FormError(say("Choose the kind of asset."))
            if not symbol:
                raise FormError(say("Enter the symbol."))
            label = (name or "").strip()
            if asset_type == "Altın":
                label = next(
                    (stored for gold, stored, _label in GOLD_KINDS if gold == symbol), label
                )
            if deduct and account_id < 0:
                raise FormError(say("Choose the account to pay from."))
            AssetPurchaseService.create_purchase(
                asset_name=label or symbol,
                asset_code=symbol,
                asset_type=asset_type,
                purchase_price=read_amount(price_text, say("unit price")),
                quantity=read_quantity(quantity_text),
                account_id=account_id if deduct else None,
                deduct_from_balance=deduct,
            )

        self._mutate(work)

    @Slot(int, str, str, int)
    def sell(self, asset_id, quantity_text, price_text, account_id):
        def work():
            from services.asset_sale_service import AssetSaleService

            if account_id < 0:
                raise FormError(say("Choose the account that receives the money."))
            quantity = read_quantity(quantity_text) if (quantity_text or "").strip() else None
            AssetSaleService.sell(
                asset_id, read_amount(price_text, say("unit price")), account_id,
                quantity=quantity,
            )

        self._mutate(work)

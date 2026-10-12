"""
Local record of what has already been issued for each Enroll Nationwide order.

Why: an order can have several lines. If line 1 is issued on eCards and line 2
fails (or the run stops before the order is marked Completed), the next run
must not issue line 1 again. Entries are removed once the order is Completed.

Item status:
  done        – issued and verified (stock dropped by exactly the quantity)
  unverified  – eCards may have issued cards but we could not confirm it.
                The automation will NOT touch this line again; a person must
                check eCards, then either mark the order Completed on
                Enroll Nationwide or delete the order's entry from this file.
"""
import os
import json
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

LEDGER_PATH = os.path.join("data", "processed_items.json")


class OrderLedger:
    def __init__(self, path: str = LEDGER_PATH):
        self.path = path
        self.data = self._load()

    # ---- persistence ----------------------------------------------------- #
    def _load(self) -> dict:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            logger.error(f"Could not read {self.path}: {e}. Starting with an empty ledger.")
            return {}

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmp, self.path)
        except OSError as e:
            logger.error(f"Could not save {self.path}: {e}")

    def _entry(self, order_id: str) -> dict:
        entry = self.data.setdefault(str(order_id), {"items": {}})
        entry["updated"] = time.time()
        return entry

    # ---- items ----------------------------------------------------------- #
    @staticmethod
    def item_key(index: int, sku: str) -> str:
        return f"{index}:{sku}"

    def item_status(self, order_id: str, key: str) -> Optional[str]:
        return self.data.get(str(order_id), {}).get("items", {}).get(key, {}).get("status")

    def mark_item(self, order_id: str, key: str, sku: str, qty: int, status: str):
        self._entry(order_id)["items"][key] = {"sku": sku, "qty": qty, "status": status, "at": time.time()}
        self._save()

    # ---- housekeeping ---------------------------------------------------- #
    def clear(self, order_id: str):
        if self.data.pop(str(order_id), None) is not None:
            self._save()

    def prune(self, open_order_ids, days: int = 60):
        """Forget old entries, but never for orders that are still open."""
        cutoff = time.time() - days * 86400
        keep = {str(o) for o in open_order_ids}
        old = [oid for oid, e in self.data.items() if oid not in keep and e.get("updated", 0) < cutoff]
        for oid in old:
            self.data.pop(oid, None)
        if old:
            self._save()


PROCESSED_ORDERS_PATH = os.path.join("data", "processed_orders.json")


class ProcessedOrders:
    """
    Permanent record of orders that are finished from the automation's point of view:
    'completed' (eCards assigned and order marked Completed) or 'skipped' (e.g. the order
    has a Certificates section, a product that isn't an eCard, or no SKU).
    Recorded orders are not opened again on later runs.
    To have an order looked at again, delete its entry from data/processed_orders.json.
    """

    def __init__(self, path: str = PROCESSED_ORDERS_PATH):
        self.path = path
        self.data = self._load()

    def _load(self) -> dict:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            logger.error(f"Could not read {self.path}: {e}. Starting with an empty record.")
            return {}

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmp, self.path)
        except OSError as e:
            logger.error(f"Could not save {self.path}: {e}")

    def is_processed(self, order_id: str) -> bool:
        return str(order_id) in self.data

    def get(self, order_id: str) -> Optional[dict]:
        return self.data.get(str(order_id))

    def record(self, order_id: str, outcome: str, reason: str = ""):
        self.data[str(order_id)] = {
            "outcome": outcome,
            "reason": reason,
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._save()

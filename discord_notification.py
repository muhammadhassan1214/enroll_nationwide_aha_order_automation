from typing import List, Dict, Any, Optional

import requests

DISCORD_DESCRIPTION_LIMIT = 4000  # Discord allows 4096 characters in an embed description


class DiscordNotifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send_notification(self, message: str) -> bool:
        if not self.webhook_url:
            print("Failed to send notification: DISCORD_WEBHOOK_URL is not set")
            return False
        if len(message) > DISCORD_DESCRIPTION_LIMIT:
            message = message[:DISCORD_DESCRIPTION_LIMIT - 20] + "\n…(truncated)"
        embed = {
            "title": "🛒 Stock Replenishment Required",
            "description": message
        }
        payload = {"embeds": [embed]}
        try:
            response = requests.post(self.webhook_url, json=payload, timeout=20)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            print(f"Failed to send notification: {e}")
            return False


def generate_stock_message(shortages: List[Dict[str, Any]], needs_review: Optional[List[str]] = None) -> Optional[str]:
    """
    Build the Discord message.
    shortages: [{'sku', 'qty' (shortage), 'required_qty', 'available_qty', 'order_name',
                 'training_site', 'instructor'}, ...]
    needs_review: orders where eCards may have issued cards that could not be confirmed.
    Returns None when there is nothing to report.
    """
    if not shortages and not needs_review:
        return None

    lines: List[str] = []
    if shortages:
        # One entry per order and product (same product twice in one order is added up)
        entries: Dict[tuple, Dict[str, Any]] = {}
        for item in shortages:
            key = (item.get("order_name", ""), item["sku"])
            entry = entries.setdefault(key, {
                "sku": item["sku"], "order_name": item.get("order_name", ""), "required": 0,
                "available": int(item.get("available_qty", 0)),
                "training_site": item.get("training_site", ""), "instructor": item.get("instructor", ""),
            })
            entry["required"] += int(item.get("required_qty", item["qty"]))
            entry["available"] = int(item.get("available_qty", entry["available"]))

        lines.append("You need to purchase the following eCards:")
        for entry in entries.values():
            to_buy = max(0, entry["required"] - entry["available"])
            order = f" ({entry['order_name']})" if entry["order_name"] else ""
            lines.append(f"• {entry['sku']} – need {entry['required']}, in stock {entry['available']}, buy {to_buy}{order}")
            if entry["training_site"] or entry["instructor"]:
                lines.append("Ordered by")
                if entry["training_site"]:
                    lines.append(f"_{entry['training_site']}_")
                if entry["instructor"]:
                    lines.append(entry["instructor"])
            lines.append("")

        # When the same product is short in several orders, show what to buy in total
        totals: Dict[str, Dict[str, int]] = {}
        for entry in entries.values():
            t = totals.setdefault(entry["sku"], {"required": 0, "available": entry["available"], "orders": 0})
            t["required"] += entry["required"]
            t["available"] = entry["available"]
            t["orders"] += 1
        multi = {sku: t for sku, t in totals.items() if t["orders"] > 1}
        if multi:
            lines.append("Total to buy:")
            for sku, t in multi.items():
                lines.append(f"• {sku} – need {t['required']} across {t['orders']} orders, "
                             f"in stock {t['available']}, buy {max(0, t['required'] - t['available'])}")
            lines.append("")

        while lines and lines[-1] == "":
            lines.pop()

    if needs_review:
        if lines:
            lines.append("")
        lines.append("**Needs a manual check:**")
        lines.extend(f"• {line}" for line in needs_review)

    return "\n".join(lines)

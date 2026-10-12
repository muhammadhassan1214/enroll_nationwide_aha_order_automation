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
    shortages: [{'sku', 'qty' (shortage), 'required_qty', 'available_qty', 'order_name'}, ...]
    needs_review: orders where eCards may have issued cards that could not be confirmed.
    Returns None when there is nothing to report.
    """
    if not shortages and not needs_review:
        return None

    lines: List[str] = []
    if shortages:
        # Total to buy per SKU, plus which orders are waiting
        totals: Dict[str, Dict[str, Any]] = {}
        for item in shortages:
            entry = totals.setdefault(item["sku"], {"required": 0, "available": int(item.get("available_qty", 0)), "orders": []})
            entry["required"] += int(item.get("required_qty", item["qty"]))
            entry["available"] = int(item.get("available_qty", entry["available"]))
            order_name = item.get("order_name", "")
            if order_name and order_name not in entry["orders"]:
                entry["orders"].append(order_name)

        lines.append("**You need to purchase the following eCards:**")
        for sku in sorted(totals):
            t = totals[sku]
            to_buy = max(0, t["required"] - t["available"])
            orders = f" ({', '.join(t['orders'])})" if t["orders"] else ""
            lines.append(f"• **{sku}** – need {t['required']}, in stock {t['available']}, **buy {to_buy}**{orders}")

    if needs_review:
        if lines:
            lines.append("")
        lines.append("**Needs a manual check:**")
        lines.extend(f"• {line}" for line in needs_review)

    return "\n".join(lines)

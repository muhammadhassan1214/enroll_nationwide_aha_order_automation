# Code Blue Order Automation (Enroll Nationwide → AHA eCards)

Issues AHA eCards on **ecards.heart.org** for certificate orders placed on **Enroll Nationwide**
(enrollnationwide.com), then marks each order **Completed**. Runs every 15 minutes.

## What each run does

1. **Stock check** – logs into eCards and reads the stock of every product (ACLS/PALS from the
   Admin Instructor page).
2. **Order retrieval** – logs into Enroll Nationwide, opens the AHA certificate orders filtered by
   status (New, Viewed, Pending – every page) and collects the links of orders that are **Paid**.
3. **Order processing** – one order at a time:
   open the order → read instructor, training site and items → check the order against the stock
   snapshot → issue the eCards in the eCards tab → validate → go back to the order (still open in
   its own tab) → select **Completed** and press *Update & send email* → next order.
4. **Notify & clean up** – Discord message listing the eCards to buy (if any order was short),
   close the browser, wait for the next run.

### Checks before an order is marked Completed
- every eCards step succeeded and eCards showed no error after Confirm/Validate or Complete
- the eCards confirmation page ("Go To Inventory") appeared
- the live eCards stock dropped by exactly the quantity assigned (ACLS/PALS: confirmation page)
- after *Update & send email* the order is reloaded and must show **Completed**

### No double assignments
`data/processed_items.json` records each order line once its eCards are assigned. If an order
stops halfway, the next run only does the remaining lines. If eCards accepted an assignment but the
stock check didn't match, the order is listed under "Needs a manual check" in Discord and the
automation leaves it alone: check eCards, then complete the order by hand (or delete its entry in
`data/processed_items.json` if nothing was issued).

### Orders are only opened once
`data/processed_orders.json` keeps every order that was **completed** or **skipped** (with the
reason, e.g. "Certificates section on the order page"). Later runs don't open those orders again.
Failed, out-of-stock, unpaid and needs-check orders are not recorded, so they are retried.
To have an order looked at again, delete its entry from that file.

### Orders that are skipped (left for a person)
Items with no SKU on the order (shown as `—`), products not listed in `data/courses.csv`
(e.g. *BLS Instructor renewal fee* or the Heartsaver eBook), Red Cross items, and unpaid orders.
There is no automatic purchasing: when stock is short the order waits and Discord lists what to buy.

## Setup

1. Run `setup.bat`.
2. Create `.env` in this folder:

   ```
   ENW_USERNAME="enroll nationwide email"
   ENW_PASSWORD="..."
   ATLAS_USERNAME="ecards login"
   ATLAS_PASSWORD="..."
   AHA_NEW_USERNAME="Code Blue ecards login"
   AHA_NEW_PASSWORD="..."
   DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."

   # optional
   DRY_RUN=true                   # read-only test run: nothing assigned or completed
   ENW_COMPLETION_MESSAGE="..."   # text added to the email the instructor receives
   ```

3. Run `run.bat`.

# Sales export requested from Right Gold

Supply **transaction-level label sales**, ideally for the last **24 complete months** plus the current month to the stock snapshot date. At minimum, provide 12 complete months. Include exact history start/end dates and confirm each branch's coverage. Separate yearly files are fine if their periods join without gaps or overlaps. Annual or monthly aggregate summaries alone are insufficient.

Required fields:

| Field | Meaning |
| --- | --- |
| Sale ID / invoice-line ID | Unique transaction identifier; preserve as text |
| Label / tag ID | Original label identity; preserve as text |
| Branch | Selling branch, explicitly mapped to NV/LN/AR/RO/IK |
| Sale date | Exact transaction date; ISO date or a real Excel date |
| Material | Gold / natural diamond / lab-grown diamond, separate categories |
| Item, karatage, variety | Same classifications as current label stock |
| Selling price | Realised price after discount, with tax basis specified |

Also include original label creation/receipt date, supplier, whole-set/tag identity, physical pieces, net gold weight, diamond carats, original landed buying cost, metal cost, stone cost, making, net sale value, discount, tax and return/cancellation status. The app's current canonical sales importer accepts completed positive sale rows; keep returns/cancellations in a separate sheet until their reversal mapping is confirmed. Do not omit returns from a net-demand analysis silently.

**Margin basis confirmed by user:** gold weight × current RG rate + making = net sale value. Plain 22KT 1.25%, plain 18KT 2.5%, Antique 15%, Jadau 30%. Use an explicitly identified net-sale-value column, never automatically substitute today's approximate sale value. Natural diamond ₹15,000/ct and lab-grown diamond ₹7,000/ct remain provisional buying assumptions; source label costs take precedence. Stone profitability needs its own confirmed basis.

Historical label sales measure observed demand and realised profit. They do not establish lost sales or availability on days with no stock. Daily/monthly stock history and item launch dates improve demand estimates and avoid misleading comparisons for recently introduced 18KT.

To measure **four annual inventory turns financially**, also supply monthly average inventory at landed cost and net COGS (including returns). Annualised units sold divided by current labels is only an indicative unit-turns proxy.

Stock-export confirmations received: `Closing Value` is full landed buying cost, `Days` is original label age, all reported HO stock is usable, and IK is confirmed zero before distribution starts. `Stone Wt` unit and the exact net-sale-value source column remain unconfirmed. Blank values remain unknown. No missing values are replaced with invented costs, stock or sales.

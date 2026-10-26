# Synthetic dataset card

Version 1.0 · generator `atlas/dataset.py` · seed 42 · scenario business clock 2026-10-26.

| Entity | Rows | Purpose |
|---|---:|---|
| Customers | 200 | Fictional profiles, size, style and tier |
| Products | 120 | Original fashion catalog across 8 categories |
| Variants | 600 | Five sizes per product, including stock-outs |
| Orders | 600 | Customer-owned purchases and item condition |
| Shipments | 600 | Synchronized simulated carrier statuses |
| Return histories | 60 | Previous size-related returns |
| Policy documents | 4 | Returns, shipping, styling and governance |

No real names, email addresses, payment credentials, customer messages, product images or proprietary catalog records are included. All data and policies were authored/generated for this case. Generated data and fictional policies are dedicated under CC0-1.0; see https://creativecommons.org/publicdomain/zero/1.0/.

Original synthetic data was chosen because the brief allows fictional documents/history and because return workflows require linked customer/order/shipment/stock data that public product-only datasets do not supply. There is no mandatory external download. Public catalog integration can be added later after checking reuse terms. No restricted H&M dataset is redistributed.

The generator uses local pseudorandom sampling, stable IDs and a checksum manifest. `seed()` verifies the files before initializing an empty database. The fixture date is fixed to keep eligibility outcomes repeatable; changing `AS_OF_DATE` affects eligibility. Do not mistake the synthetic clock for the actual current date.

Curated orders: O1001 is within 10 days of delivery (EUR 79), O1002 is within 5 days but EUR 249, O1003 is 55 days old, and O1004 belongs to a different customer and is delayed. C0001 owns O1001–O1003; C0002 owns O1004–O1006.

Limitations: sizes are apparel labels even for footwear; each order contains one line; shipping geography and tax are simplified; no actual fraud labels exist; previous returns are a review signal only. These records test software contracts and policy scenarios, not personalization effectiveness, real fraud detection or production fairness. Delivery records include a fixed estimate; only in-transit estimates are shown as non-guaranteed dates.

To regenerate: `python -m atlas.dataset`. To use another seed: `python -m atlas.dataset --seed 43 --directory /path/to/new-data`. Copy the policy directory too and point `DATA_DIR` at that tree. Use a fresh SQL database and Chroma directory for a new experiment. Startup never deletes an existing customer database.

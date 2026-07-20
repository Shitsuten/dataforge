# Example: Monthly Revenue by Category

**Prompt:** "Create a dbt model for monthly revenue by product category with refund handling"

**DataHub context used:**
- `snowflake.raw.stripe.payments` — 8 columns (payment_id, customer_id, amount, currency, status, payment_method, created_at, metadata_json)
- `snowflake.raw.shopify.orders` — 10 columns (order_id, customer_email, total_price, subtotal_price, currency, financial_status, fulfillment_status, order_date, line_items_json, discount_codes)
- `snowflake.raw.shopify.products` — 10 columns (product_id, variant_id, title, product_type, vendor, price, sku, inventory_quantity, created_at, updated_at)

**What DataForge did:**
1. Searched DataHub for datasets matching "revenue", "payments", "orders", "products"
2. Read full schemas with column types and descriptions
3. Detected that `amount` in Stripe is stored in cents (from column description) — applied `/100.0` conversion
4. Used `line_items_json` VARIANT column with Snowflake's `lateral flatten` for order line items
5. Joined on `product_id` after verifying the column exists in both orders (via line items) and products
6. Added refund handling by filtering `status = 'refunded'` from payments
7. Generated schema YAML with appropriate tests (not_null on all output columns)
8. Validated all column references against the actual DataHub schemas

**Validation result:** ✓ All column references verified, correct Snowflake dialect, PII columns excluded from output

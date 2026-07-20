# Example: Data Freshness Check

**Prompt:** "Check data freshness for all tier-1 datasets"

**Output type:** SQL query (not dbt model)

**DataHub context used:**
- Searched for datasets tagged `tier-1`
- Found 3 matching datasets: payments, orders, customers
- Read primary key columns (NOT NULL constraint) and timestamp columns for freshness checks
- Generated a UNION ALL query that checks each table's latest record timestamp

**What DataForge did:**
1. Identified tier-1 datasets from DataHub tags
2. Found the timestamp column in each table (created_at, order_date, created_at)
3. Found the primary key column in each table (payment_id, order_id, customer_id) — all marked NOT NULL
4. Generated freshness classification: FRESH (<1h), OK (<24h), STALE (<72h), CRITICAL (>72h)
5. Added null key count as a bonus data quality check
6. Used correct Snowflake dialect (datediff, current_timestamp())

**Validation result:** ✓ All column references verified, correct types, proper NULL handling

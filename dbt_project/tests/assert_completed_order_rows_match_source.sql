-- Singular business test: completed_order_rows in fct_daily_revenue must equal
-- the actual number of completed orders per day in stg_orders. A customer
-- dimension with more than one active row for the same customer_id makes the
-- join in fct_daily_revenue.sql fan out and inflate this count with no SQL
-- error -- this reconciliation is the guardrail against that failure mode.
with source_counts as (
    select order_date, count(*) as source_completed_orders
    from {{ ref('stg_orders') }}
    where status = 'completed'
    group by 1
)
select
    f.order_date,
    f.completed_order_rows,
    s.source_completed_orders
from {{ ref('fct_daily_revenue') }} f
join source_counts s on f.order_date = s.order_date
where f.completed_order_rows != s.source_completed_orders

-- 003: ready-made answers. Every view is per store, so a second location needs no new code.
CREATE VIEW v_item_rank AS
  SELECT w.store_id, w.week, i.grp, i.name, w.units_sold,
         RANK() OVER (PARTITION BY w.store_id, w.week, i.grp ORDER BY w.units_sold DESC) AS rk
  FROM menu_week w JOIN menu_item i USING (item_id) WHERE w.units_sold IS NOT NULL;

CREATE VIEW v_vs_last_week AS
  SELECT a.store_id, a.week, a.sales, a.sales - b.sales AS sales_change, a.net_profit, a.net_profit - b.net_profit AS profit_change,
         a.cups_hot + a.cups_cold AS cups, (a.cups_hot + a.cups_cold) - (b.cups_hot + b.cups_cold) AS cups_change
  FROM store_week a LEFT JOIN store_week b ON b.store_id = a.store_id AND b.week = a.week - 1;

CREATE VIEW v_open_decisions AS SELECT decision_id, week, title, status, ceo_note FROM decision WHERE status IN ('open','unknown');

CREATE VIEW v_store_compare AS
  SELECT w.week, s.name AS store, w.sales, w.net_profit, w.cups_hot + w.cups_cold AS cups, w.rating_overall, w.wage, w.staff_count, w.staff_morale
  FROM store_week w JOIN store s USING (store_id);

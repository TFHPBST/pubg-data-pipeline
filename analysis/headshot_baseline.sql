SELECT
    count(*) AS human_kills,
    round(avg(is_headshot::int), 3) AS hs_ratio_all,
    round(
        (count(*) FILTER (WHERE kill_type <> 'finished' AND is_headshot))::numeric
        / count(*) FILTER (WHERE kill_type <> 'finished'),
        3
    ) AS hs_ratio_own,
    round(
        (count(*) FILTER (WHERE kill_type = 'finished' AND is_headshot))::numeric
        / NULLIF(count(*) FILTER (WHERE kill_type = 'finished'), 0),
        3
    ) AS hs_ratio_finished
FROM kills
WHERE killer LIKE 'account.%'
  AND victim LIKE 'account.%';
 with qualified as(
    select 
        * 
        from player_stats 
        where own_kills >= 8), 
rank as(
    select
        *, 
        percent_rank() over (order by own_hs_ratio) as hs_rank, 
        percent_rank() over (order by kills_per_match) as kpm_rank 
        from qualified) 
select 
    'p_' || left(md5(account_id), 8) as player, 
    matches_played, 
    own_kills, 
    own_hs_ratio, 
    kills_per_match, 
    finished_share,
    round(hs_rank::numeric, 2) as hs_rank, 
    round(kpm_rank::numeric, 2) as kpm_rank 
    from rank 
    order by hs_rank + kpm_rank desc, player 
    limit 10;
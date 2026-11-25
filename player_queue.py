import psycopg

from load import get_conninfo


def seed_queue(cur):
    """participants의 사람 플레이어를 대기열에 넣고, 새로 들어간 인원 수를 돌려준다."""
    cur.execute(
        """
        INSERT INTO player_queue (account_id)
        SELECT DISTINCT account_id
        FROM participants
        WHERE account_id LIKE 'account.%'
        ON CONFLICT (account_id) DO NOTHING
        """
    )
    return cur.rowcount


def next_batch(cur, n=10):
    """다음에 수집할 플레이어의 account_id를 최대 n명 돌려준다."""
    cur.execute(
        """
        SELECT account_id
        FROM player_queue
        WHERE NOT (status = 'failed' AND attempts >= 3)
        AND (last_collected_at IS NULL OR last_collected_at < now() - interval '1 day')
        ORDER BY last_collected_at NULLS FIRST, account_id
        LIMIT %s
        """,
        (n,),
    )
    return [row[0] for row in cur.fetchall()]


def mark_done(cur, account_ids):
    """수집에 성공한 플레이어들을 done으로 바꾸고, 바뀐 행 수를 돌려준다."""
    cur.execute(
        """
        UPDATE player_queue
        SET status = 'done', last_collected_at = NOW(), attempts = 0, last_error = NULL
        WHERE account_id = ANY(%s)
        """,
        (account_ids,),
    )
    return cur.rowcount


def mark_failed(cur, account_id, error):
    """수집에 실패한 플레이어의 시도 횟수를 늘리고 오류를 기록한다."""
    cur.execute(
        """
        UPDATE player_queue
        SET status = 'failed', attempts = attempts + 1, last_error = %s,
            last_collected_at = NOW()
        WHERE account_id = %s
        """,
        (error, account_id),
    )


if __name__ == "__main__":
    with psycopg.connect(get_conninfo()) as conn:
        with conn.cursor() as cur:
            print(f"새로 추가: {seed_queue(cur)}명")

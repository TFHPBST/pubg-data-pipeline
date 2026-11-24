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
        ORDER BY last_collected_at NULLS FIRST, account_id
        LIMIT %s
        """,
        (n,),
    )
    return [row[0] for row in cur.fetchall()]


if __name__ == "__main__":
    with psycopg.connect(get_conninfo()) as conn:
        with conn.cursor() as cur:
            print(f"새로 추가: {seed_queue(cur)}명")

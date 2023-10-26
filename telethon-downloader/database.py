import sqlite3

from env import *

# ------------ INIT DATABASE ---------------
db = None
if db is None:
    db = sqlite3.connect(TG_SQLITE_FILE)
    db.execute(
        'CREATE TABLE IF NOT EXISTS locations(id INTEGER PRIMARY KEY, location varchar(500) NOT NULL, '
        'message_id varchar(50) NOT NULL, display_location varchar(500), messages_ids varchar(50000),'
        'is_subscription BOOLEAN DEFAULT FALSE)')
    db.execute(
        'CREATE TABLE IF NOT EXISTS subscriptions (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, '
        'chat_id varchar(50) NOT NULL, location varchar(500) NOT NULL, display_name varchar(500) NOT NULL)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_location ON locations(location)')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_subscription_unique ON subscriptions(user_id, chat_id)')
    db.execute('DELETE FROM locations')
    db.commit()

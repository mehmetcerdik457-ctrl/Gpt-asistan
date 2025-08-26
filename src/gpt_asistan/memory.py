import sqlite3, os, json, time
DB_PATH = os.getenv("GA_DB_PATH", "memory.db")

def _conn():
    return sqlite3.connect(DB_PATH)

def init():
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            ts REAL NOT NULL
        )""")

def add(session:str, role:str, content:str):
    with _conn() as c:
        c.execute("INSERT INTO messages(session,role,content,ts) VALUES (?,?,?,?)",
                  (session, role, content, time.time()))

def history(session:str, limit:int=50):
    with _conn() as c:
        cur=c.execute("SELECT role,content FROM messages WHERE session=? ORDER BY id DESC LIMIT ?", (session, limit))
        rows=cur.fetchall()
    rows.reverse()
    return [{"role":r,"content":c} for r,c in rows]

def export_jsonl(path:str="memory.jsonl"):
    with _conn() as c, open(path,"w",encoding="utf-8") as f:
        for (sess, role, content, ts) in c.execute("SELECT session,role,content,ts FROM messages ORDER BY id"):
            f.write(json.dumps({"session":sess,"role":role,"content":content,"ts":ts}, ensure_ascii=False)+"\n")

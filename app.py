import sqlite3
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-secret-key"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

DB = "pycord.db"

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS friendships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        friend_id INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        UNIQUE(user_id, friend_id)
    );
    CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        owner_id INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS group_members (
        group_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        UNIQUE(group_id, user_id)
    );
    """)
    conn.commit()
    conn.close()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

@app.route("/")
def index():
    return redirect(url_for("dashboard") if "user_id" in session else url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if len(username) < 3 or len(password) < 6:
            return render_template("register.html", error="Usuário deve ter 3+ caracteres e senha 6+.")
        conn = db()
        try:
            cur = conn.execute(
                "INSERT INTO users(username,password_hash) VALUES(?,?)",
                (username, generate_password_hash(password))
            )
            conn.commit()
            session["user_id"] = cur.lastrowid
            session["username"] = username
            return redirect(url_for("dashboard"))
        except sqlite3.IntegrityError:
            return render_template("register.html", error="Esse usuário já existe.")
        finally:
            conn.close()
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = db()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Usuário ou senha inválidos.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", username=session["username"])

@app.get("/api/users")
@login_required
def users():
    q = request.args.get("q", "").strip()
    conn = db()
    rows = conn.execute(
        "SELECT id, username FROM users WHERE username LIKE ? AND id != ? LIMIT 20",
        (f"%{q}%", session["user_id"])
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.post("/api/friends/request")
@login_required
def friend_request():
    friend_id = int(request.json["friend_id"])
    if friend_id == session["user_id"]:
        return jsonify({"error": "Você não pode adicionar a si mesmo."}), 400
    conn = db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO friendships(user_id,friend_id,status) VALUES(?,?,?)",
            (session["user_id"], friend_id, "accepted")
        )
        conn.execute(
            "INSERT OR IGNORE INTO friendships(user_id,friend_id,status) VALUES(?,?,?)",
            (friend_id, session["user_id"], "accepted")
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})

@app.get("/api/friends")
@login_required
def get_friends():
    conn = db()
    rows = conn.execute("""
        SELECT u.id, u.username
        FROM users u
        JOIN friendships f ON f.friend_id=u.id
        WHERE f.user_id=? AND f.status='accepted'
        ORDER BY u.username
    """, (session["user_id"],)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.post("/api/groups")
@login_required
def create_group():
    name = request.json.get("name", "").strip()
    if not name:
        return jsonify({"error": "Nome obrigatório."}), 400
    conn = db()
    cur = conn.execute("INSERT INTO groups(name,owner_id) VALUES(?,?)", (name, session["user_id"]))
    gid = cur.lastrowid
    conn.execute("INSERT INTO group_members(group_id,user_id) VALUES(?,?)", (gid, session["user_id"]))
    conn.commit()
    conn.close()
    return jsonify({"id": gid, "name": name})

@app.get("/api/groups")
@login_required
def groups():
    conn = db()
    rows = conn.execute("""
        SELECT g.id,g.name
        FROM groups g
        JOIN group_members gm ON gm.group_id=g.id
        WHERE gm.user_id=?
        ORDER BY g.id DESC
    """, (session["user_id"],)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.post("/api/groups/<int:gid>/add")
@login_required
def add_group_member(gid):
    friend_id = int(request.json["user_id"])
    conn = db()
    is_friend = conn.execute(
        "SELECT 1 FROM friendships WHERE user_id=? AND friend_id=? AND status='accepted'",
        (session["user_id"], friend_id)
    ).fetchone()
    owner = conn.execute(
        "SELECT 1 FROM groups WHERE id=? AND owner_id=?",
        (gid, session["user_id"])
    ).fetchone()
    if not is_friend or not owner:
        conn.close()
        return jsonify({"error": "Você precisa ser amigo da pessoa e dono do grupo."}), 403
    conn.execute("INSERT OR IGNORE INTO group_members(group_id,user_id) VALUES(?,?)", (gid, friend_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@socketio.on("join")
def on_join(data):
    room = str(data.get("room"))
    join_room(room)
    emit("system", {"message": f"{session.get('username','Usuário')} entrou na sala."}, to=room)

@socketio.on("message")
def on_message(data):
    room = str(data.get("room"))
    text = str(data.get("message", "")).strip()
    if text:
        emit("message", {"username": session.get("username","Usuário"), "message": text}, to=room)

# WebRTC signaling
@socketio.on("webrtc")
def webrtc(data):
    room = str(data.get("room"))
    payload = dict(data)
    payload.pop("room", None)
    emit("webrtc", payload, to=room, include_self=False)

if __name__ == "__main__":
    init_db()
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)

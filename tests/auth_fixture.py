"""Authenticated actors for isolated integration databases only."""

import http.cookiejar
import json
import urllib.request


def insert_admin(db, encoded, academia_id=1, user_id=100, email="admin@example.test"):
    db.execute("INSERT INTO perfil (id, nome) VALUES (90, 'Administrador') "
               "ON CONFLICT(nome) DO NOTHING")
    perfil_id = db.execute("SELECT id FROM perfil WHERE nome='Administrador'").fetchone()[0]
    db.execute("INSERT INTO usuario (id, academia_id, perfil_id, nome, email, senha_hash) "
               "VALUES (?, ?, ?, 'Administrador de teste', ?, ?)",
               (user_id, academia_id, perfil_id, email, encoded))


def login_client(base, academia_id=1, email="admin@example.test"):
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    request = urllib.request.Request(base + "/api/auth/login", method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"academia_id": academia_id, "email": email,
                         "senha": "TH24-test-password"}).encode())
    with client.open(request, timeout=20) as response:
        assert response.code == 200
    return client

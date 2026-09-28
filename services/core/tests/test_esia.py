"""Вход через Госуслуги в mock-режиме: весь путь браузера, но без браузера."""

from urllib.parse import parse_qs, urlparse

import pytest

from app.auth.esia import snils as snils_lib
from tests.conftest import login

REDIRECT = "http://localhost:5173/auth/esia/callback"
DOCTOR_SNILS = snils_lib.make("200300400")  # = Лебедева в MOCK_PERSONS


def test_snils_checksum():
    assert snils_lib.normalize("112-233-445 95") == "11223344595"
    with pytest.raises(snils_lib.InvalidSnilsError):
        snils_lib.normalize("112-233-445 96")
    with pytest.raises(snils_lib.InvalidSnilsError):
        snils_lib.normalize("123")
    assert snils_lib.format_snils("11223344595") == "112-233-445 95"


async def _esia_login(client, login_value: str, password: str = "esia12345"):
    start = await client.get("/api/v1/auth/esia/start", params={"redirect_uri": REDIRECT})
    assert start.status_code == 200, start.text
    state = start.json()["state"]
    assert "/esia-test/login" in start.json()["url"]

    auth = await client.post(
        "/api/v1/esia-test/authorize",
        json={"login": login_value, "password": password, "redirect_uri": REDIRECT, "state": state},
    )
    if auth.status_code != 200:
        return auth
    q = parse_qs(urlparse(auth.json()["redirect"]).query)
    assert q["state"] == [state]
    return await client.post(
        "/api/v1/auth/esia/callback", json={"code": q["code"][0], "state": state, "redirect_uri": REDIRECT}
    )


async def test_esia_full_flow_binds_by_snils(client):
    admin = await login(client, "admin")
    users = (await client.get("/api/v1/users", headers=admin)).json()
    doctor = next(u for u in users if u["email"] == "doctor@test.ru")
    bad = await client.patch(f"/api/v1/users/{doctor['id']}", headers=admin, json={"snils": "200-300-400 00"})
    assert bad.status_code == 422  # неверное контрольное число
    ok = await client.patch(f"/api/v1/users/{doctor['id']}", headers=admin, json={"snils": DOCTOR_SNILS})
    assert ok.status_code == 200 and ok.json()["snils"] == DOCTOR_SNILS

    resp = await _esia_login(client, "200-300-400 " + DOCTOR_SNILS[-2:])  # вход по СНИЛС
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["email"] == "doctor@test.ru"
    assert me.json()["esia_linked"] is True

    again = await _esia_login(client, "lebedeva@example.ru")  # повторно, по email — уже по oid
    assert again.status_code == 200


async def test_esia_rejects_unknown_person_and_bad_password(client):
    unknown = await _esia_login(client, "smirnov@example.ru")
    assert unknown.status_code == 403
    assert "СНИЛС" in unknown.json()["detail"]
    wrong = await _esia_login(client, "smirnov@example.ru", password="nope")
    assert wrong.status_code == 401


async def test_esia_guards(client):
    evil = await client.get("/api/v1/auth/esia/start", params={"redirect_uri": "https://evil.example/cb"})
    assert evil.status_code == 400
    forged = await client.post(
        "/api/v1/auth/esia/callback", json={"code": "x", "state": "forged", "redirect_uri": REDIRECT}
    )
    assert forged.status_code == 400
    cfg = await client.get("/api/v1/auth/esia/config")
    assert cfg.json() == {"enabled": True, "mode": "mock"}

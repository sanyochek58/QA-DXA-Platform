from tests.conftest import fake_dicom, fake_ml, login


async def test_login_and_me(client):
    bad = await client.post("/api/v1/auth/login", data={"username": "lab@test.ru", "password": "wrong-pass"})
    assert bad.status_code == 401
    missing = await client.post(
        "/api/v1/auth/login", data={"username": "nobody@test.ru", "password": "x" * 9}
    )
    assert missing.status_code == 401

    headers = await login(client, "lab")
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["role"] == "technologist"
    assert me.json()["last_login_at"] is not None
    assert "password_hash" not in me.json()


async def test_invalid_token(client):
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 401


async def test_role_guards(client):
    lab = await login(client, "lab")
    doctor = await login(client, "doctor")
    admin = await login(client, "admin")
    assert (await client.get("/api/v1/users", headers=lab)).status_code == 403
    assert (await client.get("/api/v1/users", headers=doctor)).status_code == 403
    assert (await client.get("/api/v1/stats/summary", headers=lab)).status_code == 403
    assert (await client.get("/api/v1/studies/queue", headers=lab)).status_code == 403
    users = await client.get("/api/v1/users", headers=admin)
    assert users.status_code == 200 and len(users.json()) >= 4


async def test_admin_creates_and_blocks_user(client):
    admin = await login(client, "admin")
    created = await client.post(
        "/api/v1/users",
        headers=admin,
        json={
            "email": "New.User@Test.ru",
            "full_name": "Новый",
            "password": "longenough1",
            "role": "technologist",
        },
    )
    assert created.status_code == 201
    assert created.json()["email"] == "new.user@test.ru"
    dup = await client.post(
        "/api/v1/users",
        headers=admin,
        json={
            "email": "new.user@test.ru",
            "full_name": "Дубль",
            "password": "longenough1",
            "role": "technologist",
        },
    )
    assert dup.status_code == 409
    uid = created.json()["id"]
    blocked = await client.patch(f"/api/v1/users/{uid}", headers=admin, json={"is_active": False})
    assert blocked.json()["is_active"] is False
    login_blocked = await client.post(
        "/api/v1/auth/login", data={"username": "new.user@test.ru", "password": "longenough1"}
    )
    assert login_blocked.status_code == 401


async def test_upload_rejects_non_dicom(client):
    lab = await login(client, "lab")
    resp = await client.post(
        "/api/v1/studies",
        headers=lab,
        files=[("files", ("x.dcm", b"not a dicom at all", "application/dicom"))],
    )
    assert resp.status_code == 422


async def test_full_study_flow(client):
    lab = await login(client, "lab")
    lab2 = await login(client, "lab2")
    doctor = await login(client, "doctor")
    admin = await login(client, "admin")

    resp = await client.post(
        "/api/v1/studies",
        headers=lab,
        data={"title": "Пациент 1"},
        files=[
            ("files", ("a.dcm", fake_dicom(), "application/dicom")),
            ("files", ("b.dcm", fake_dicom(), "application/dicom")),
        ],
    )
    assert resp.status_code == 202, resp.text
    sid = resp.json()["id"]

    # Фоновая задача в тестовом клиенте выполняется до возврата ответа
    study = (await client.get(f"/api/v1/studies/{sid}", headers=lab)).json()
    assert study["status"] == "done"
    assert study["quality_ok"] is False
    assert study["violation_codes"] == ["SPINE_AXIS"]
    assert study["review_status"] == "pending"
    assert study["n_images"] == 2

    # Чужое исследование лаборанту не видно, причём 404, а не 403
    assert (await client.get(f"/api/v1/studies/{sid}", headers=lab2)).status_code == 404
    own = await client.get("/api/v1/studies", headers=lab2)
    assert all(s["id"] != sid for s in own.json()["items"])

    # Фильтры списка
    bad_only = await client.get("/api/v1/studies?quality_ok=false&code=SPINE_AXIS", headers=admin)
    assert any(s["id"] == sid for s in bad_only.json()["items"])

    queue = await client.get("/api/v1/studies/queue", headers=doctor)
    assert any(s["id"] == sid for s in queue.json()["items"])

    # Лаборант не может ставить решение врача
    assert (
        await client.post(f"/api/v1/studies/{sid}/review", headers=lab, json={"quality_ok": True})
    ).status_code == 403
    reviewed = await client.post(
        f"/api/v1/studies/{sid}/review",
        headers=doctor,
        json={"quality_ok": True, "comment": "Наклон в пределах нормы"},
    )
    assert reviewed.json()["review_status"] == "corrected"
    assert reviewed.json()["reviewed_by"]["full_name"] == "doctor"

    stats = (await client.get("/api/v1/stats/summary", headers=admin)).json()
    assert stats["total"] >= 1
    assert stats["reviewed"] >= 1
    assert any(c["code"] == "SPINE_AXIS" for c in stats["by_code"])
    assert any(o["total"] >= 1 for o in stats["by_operator"])


async def test_ml_failure_marks_study_failed(client):
    lab = await login(client, "lab")
    fake_ml.fail = True
    try:
        resp = await client.post(
            "/api/v1/studies", headers=lab, files=[("files", ("a.dcm", fake_dicom(), "application/dicom"))]
        )
        study = (await client.get(f"/api/v1/studies/{resp.json()['id']}", headers=lab)).json()
        assert study["status"] == "failed"
        assert "недоступен" in study["error"]
    finally:
        fake_ml.fail = False
    again = await client.post(f"/api/v1/studies/{study['id']}/reanalyze", headers=lab)
    assert again.status_code == 202
    assert (await client.get(f"/api/v1/studies/{study['id']}", headers=lab)).json()["status"] == "done"


async def test_batch_requires_reviewer_and_zip(client):
    lab = await login(client, "lab")
    doctor = await login(client, "doctor")
    files = {"archive": ("s.zip", b"PK\x05\x06" + b"\0" * 18, "application/zip")}
    assert (await client.post("/api/v1/studies/batch", headers=lab, files=files)).status_code == 403
    not_zip = {"archive": ("s.txt", b"x", "text/plain")}
    assert (await client.post("/api/v1/studies/batch", headers=doctor, files=not_zip)).status_code == 422
    ok = await client.post("/api/v1/studies/batch", headers=doctor, files=files)
    assert ok.status_code == 200
    assert ok.headers["content-type"] == "application/zip"

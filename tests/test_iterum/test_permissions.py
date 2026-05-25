"""Tests de permisos: matriz rol vs endpoint."""


def test_asesor_blocked_from_iterum(login_as, user_asesor):
    client = login_as(user_asesor)
    r = client.get('/iterum/dashboard')
    assert r.status_code == 403


def test_supervisor_can_view_dashboard(login_as, user_supervisor):
    client = login_as(user_supervisor)
    r = client.get('/iterum/dashboard')
    assert r.status_code == 200


def test_supervisor_cannot_upload(login_as, user_supervisor):
    client = login_as(user_supervisor)
    r = client.get('/iterum/upload')
    assert r.status_code == 403


def test_analista_can_upload(login_as, user_analista):
    client = login_as(user_analista)
    r = client.get('/iterum/upload')
    assert r.status_code == 200


def test_superadmin_can_create_report_snapshot(login_as, user_superadmin):
    client = login_as(user_superadmin)
    r = client.post('/iterum/api/report/snapshot',
                    json={'period_label': 'Test'},
                    headers={'Content-Type': 'application/json'})
    assert r.status_code in (200, 201)


def test_analista_cannot_create_report_snapshot(login_as, user_analista):
    client = login_as(user_analista)
    r = client.post('/iterum/api/report/snapshot',
                    json={'period_label': 'Test'},
                    headers={'Content-Type': 'application/json'})
    assert r.status_code == 403


def test_supervisor_cannot_audit(login_as, user_supervisor):
    client = login_as(user_supervisor)
    r = client.post('/iterum/api/audit/1',
                    json={'verdict': 'ok'},
                    headers={'Content-Type': 'application/json'})
    assert r.status_code == 403


def test_access_log_only_superadmin(login_as, user_analista, user_superadmin):
    client_an = login_as(user_analista)
    r = client_an.get('/iterum/api/access-log')
    assert r.status_code == 403

    client_sa = login_as(user_superadmin)
    r = client_sa.get('/iterum/api/access-log')
    assert r.status_code == 200

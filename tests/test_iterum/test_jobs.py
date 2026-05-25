"""Tests del job de procesamiento (ejecutado sincronicamente para testing)."""


def test_process_upload_inserts_surveys(app, user_analista, sample_xlsx):
    from models import db
    from iterum.models import NPSUpload, NPSSurvey
    from iterum.services.jobs import _process_upload
    from iterum.services.dedup import file_hash

    with app.app_context():
        upload = NPSUpload(
            uploaded_by_id=user_analista.id,
            filename='test.xlsx',
            file_hash=file_hash(sample_xlsx),
            status='pending',
        )
        db.session.add(upload)
        db.session.commit()
        upload_id = upload.id

    with app.app_context():
        _process_upload(upload_id, sample_xlsx)

    with app.app_context():
        upload = db.session.get(NPSUpload, upload_id)
        assert upload.status == 'done'
        assert upload.rows_new == 5
        assert upload.rows_duplicate == 0
        assert upload.rows_invalid == 0
        assert NPSSurvey.query.count() == 5


def test_process_upload_dedupe_on_second_run(app, user_analista, sample_xlsx):
    """Mismo archivo dos veces => 0 nuevas la segunda."""
    from models import db
    from iterum.models import NPSUpload, NPSSurvey
    from iterum.services.jobs import _process_upload
    from iterum.services.dedup import file_hash
    import shutil
    import tempfile
    import os

    fhash = file_hash(sample_xlsx)

    with app.app_context():
        u1 = NPSUpload(uploaded_by_id=user_analista.id, filename='a.xlsx',
                       file_hash=fhash, status='pending')
        db.session.add(u1); db.session.commit()
        u1_id = u1.id

    with app.app_context():
        _process_upload(u1_id, sample_xlsx)
        assert NPSSurvey.query.count() == 5

    # Segunda carga: copia el archivo para que el job pueda borrarlo
    tmp = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
    tmp.close()
    shutil.copy(sample_xlsx, tmp.name)

    with app.app_context():
        u2 = NPSUpload(uploaded_by_id=user_analista.id, filename='b.xlsx',
                       file_hash=fhash + 'x', status='pending')
        db.session.add(u2); db.session.commit()
        u2_id = u2.id

    with app.app_context():
        _process_upload(u2_id, tmp.name)
        u2 = db.session.get(NPSUpload, u2_id)
        assert u2.status == 'done'
        assert u2.rows_new == 0
        assert u2.rows_duplicate == 5
        assert NPSSurvey.query.count() == 5

    if os.path.exists(tmp.name):
        os.remove(tmp.name)


def test_upload_endpoint_allows_retry_after_failure(app, login_as, user_analista, sample_xlsx):
    """Regression: si el primer upload del archivo X fallo, subir X de nuevo
    debe procesarlo (no devolver duplicate_file)."""
    from models import db
    from iterum.models import NPSUpload
    from iterum.services.dedup import file_hash

    fhash = file_hash(sample_xlsx)

    # Simular un upload previo que fallo
    with app.app_context():
        failed = NPSUpload(
            uploaded_by_id=user_analista.id,
            filename='oldname.xlsx',
            file_hash=fhash,
            status='failed',
            error_message='Faltan columnas obligatorias (parser viejo)',
        )
        db.session.add(failed); db.session.commit()
        failed_id = failed.id

    client = login_as(user_analista)
    with open(sample_xlsx, 'rb') as f:
        r = client.post('/iterum/api/upload',
                        data={'file': (f, 'newname.xlsx')},
                        content_type='multipart/form-data')
    assert r.status_code == 202, f"Expected 202, got {r.status_code}: {r.data}"
    body = r.get_json()
    assert not body.get('duplicate_file'), 'Deberia haber procesado de nuevo, no marcar como duplicado'
    assert body['status'] == 'pending'

    # No quedan uploads en estado failed para este hash; el nuevo es distinto
    # (id puede coincidir si SQLite reusa autoincrement)
    with app.app_context():
        assert NPSUpload.query.filter_by(file_hash=fhash, status='failed').count() == 0
        new_upload = db.session.get(NPSUpload, body['upload_id'])
        assert new_upload is not None
        assert new_upload.filename == 'newname.xlsx'


def test_upload_endpoint_blocks_duplicate_when_done(app, login_as, user_analista, sample_xlsx):
    """Si el upload previo termino bien (done), no se reprocesa."""
    from models import db
    from iterum.models import NPSUpload
    from iterum.services.dedup import file_hash

    fhash = file_hash(sample_xlsx)
    with app.app_context():
        done = NPSUpload(
            uploaded_by_id=user_analista.id, filename='x.xlsx',
            file_hash=fhash, status='done', rows_new=10,
        )
        db.session.add(done); db.session.commit()
        done_id = done.id

    client = login_as(user_analista)
    with open(sample_xlsx, 'rb') as f:
        r = client.post('/iterum/api/upload',
                        data={'file': (f, 'x.xlsx')},
                        content_type='multipart/form-data')
    assert r.status_code == 200
    body = r.get_json()
    assert body['duplicate_file'] is True
    assert body['upload_id'] == done_id


def test_delete_upload_cascades_surveys(app, login_as, user_analista, sample_xlsx):
    """DELETE /api/upload/<id> borra el upload Y sus surveys asociadas."""
    from models import db
    from iterum.models import NPSUpload, NPSSurvey
    from iterum.services.jobs import _process_upload
    from iterum.services.dedup import file_hash

    fhash = file_hash(sample_xlsx)
    with app.app_context():
        u = NPSUpload(uploaded_by_id=user_analista.id, filename='x.xlsx',
                      file_hash=fhash, status='pending')
        db.session.add(u); db.session.commit()
        upload_id = u.id
        _process_upload(upload_id, sample_xlsx)
        assert NPSSurvey.query.filter_by(upload_id=upload_id).count() == 5

    client = login_as(user_analista)
    r = client.delete(f'/iterum/api/upload/{upload_id}')
    assert r.status_code == 200
    body = r.get_json()
    assert body['deleted'] is True
    assert body['surveys_deleted'] == 5

    with app.app_context():
        assert db.session.get(NPSUpload, upload_id) is None
        assert NPSSurvey.query.filter_by(upload_id=upload_id).count() == 0


def test_delete_upload_requires_editor(app, login_as, user_supervisor):
    """Supervisor no puede eliminar uploads."""
    client = login_as(user_supervisor)
    r = client.delete('/iterum/api/upload/9999')
    assert r.status_code == 403

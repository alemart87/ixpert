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

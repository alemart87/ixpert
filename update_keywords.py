"""
Update keywords for all content by extracting terms from HTML body.
Adds auto-extracted keywords while preserving existing ones.
Run once to enrich the search index.
"""
import re
from app import app, db
from models import Content

# Manual keyword enrichment for known content
EXTRA_KEYWORDS = {
    'tuto4': 'tarjeta, activacion, seguridad, transaccion, pin transaccion',
    'tuto5': 'devolucion, reembolso, comercio, transaccion, online',
    'tuto6': 'pago duplicado, tarjeta credito, debito automatico, tc',
    'tuto7': 'tarjeta fisica, envio, entrega, delivery, courier',
    'tuto8': 'contracargo, tarjeta credito, tarjeta debito, disputa, fraude, cargo, tc, td',
    'tuto9': 'cuenta bancaria, tarjeta debito, ahorro, corriente, salario, pgs, mantenimiento, apertura',
    'tuto10': 'pin acceso, clave, contraseña',
    'intervale': 'intervale, cuenta, tarjeta debito',
    'tarifario': 'tarifario, comisiones, costos, tarjeta',
    'saccom': 'sac, saccom, plataforma, sistema, gestion',
    'bancard': 'bancard, tarjeta, pos, terminal',
    'alias': 'alias, transferencia, nombre, itau',
    'resumentc': 'resumen, tarjeta credito, extracto, tc, estado cuenta',
    'tipificaciones': 'tipificacion, registro, saccom, codigo, clasificacion',
    'phishing': 'phishing, fraude, seguridad, estafa, correo, email, sospechoso',
    'herramientas': 'herramientas, plataformas, bancard, saccom, bpm, snpi, extranet',
    'depositarcheque': 'cheque, deposito, app, movil, celular',
    'sihb': 'sihb, empresas, banca empresas, corporativo',
    'nucleo': 'nucleo, ventas, sistema, core bancario',
    'bpm': 'bpm, proceso, gestion, workflow, excepcional',
    'bpm-excepcion': 'itoken, excepcional, excepcion, bpm, token',
    'prestamo': 'prestamo, credito, cuota, financiamiento',
    'ahorroprogramado': 'ahorro programado, ahorro, debito automatico',
    'snpi': 'snpi, transferencia, pago, interbancario',
    'ptelectronica': 'pt electronica, plataforma, transferencia',
    'extranet': 'extranet, portal, acceso',
    'admin24hs': 'admin, 24hs, administracion',
    'cnb': 'cnb, agencia, sucursal, direccion, horario, atencion',
    'qrpix': 'pix, qr, transferencia, brasil, internacional',
    'calculadora-nps-2-0': 'nps, calculadora, encuesta, satisfaccion',
    'cancelartransferencia': 'cancelar, transferencia programada, anular',
    'aumentolineatc': 'aumento, linea, tarjeta credito, limite, tc',
    'extractotc': 'extracto, tarjeta credito, descargar, tc, resumen',
    'extractoxmail': 'extracto, mail, email, correo, resumen',
    'game1': 'trivia, juego, quiz, conocimiento',
    'retencionyreubicacion': 'retencion, reubicacion, cliente',
    'pinactivate': 'pin, activacion, filtro, proceso, guia',
    'matriz-soporte': 'matriz, soporte, sihb, gestion',
    'matriz-cib': 'matriz, cib, gestion, empresas',
    'anulacionesyconfirmaciones': 'anulacion, confirmacion, pronet, netel, bancard',
}


def extract_keywords_from_html(html):
    """Extract potential keywords from HTML headings and bold text."""
    keywords = set()

    # Extract from headings
    for m in re.finditer(r'<h[1-6][^>]*>(.*?)</h[1-6]>', html, re.IGNORECASE | re.DOTALL):
        text = re.sub(r'<[^>]+>', '', m.group(1)).strip().lower()
        if text and len(text) < 100:
            keywords.add(text)

    # Extract from bold/strong text
    for m in re.finditer(r'<(?:b|strong)[^>]*>(.*?)</(?:b|strong)>', html, re.IGNORECASE | re.DOTALL):
        text = re.sub(r'<[^>]+>', '', m.group(1)).strip().lower()
        if text and 3 < len(text) < 60:
            keywords.add(text)

    return ', '.join(list(keywords)[:20])


def update():
    with app.app_context():
        contents = Content.query.all()
        updated = 0

        for c in contents:
            existing = (c.keywords or '').strip()
            extra = EXTRA_KEYWORDS.get(c.slug, '')
            auto = extract_keywords_from_html(c.html_content)

            # Merge all keywords, deduplicate
            all_kw = set()
            for source in [existing, extra, auto]:
                for kw in source.split(','):
                    kw = kw.strip().lower()
                    if kw and len(kw) > 1:
                        all_kw.add(kw)

            new_keywords = ', '.join(sorted(all_kw))
            if new_keywords != existing:
                c.keywords = new_keywords
                updated += 1
                print(f"  Updated [{c.slug}]: {len(all_kw)} keywords")

        db.session.commit()
        print(f"Updated {updated}/{len(contents)} content items.")


if __name__ == '__main__':
    update()

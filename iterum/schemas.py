"""Validacion liviana de payloads sin dependencias externas (pydantic-free)."""
from datetime import date, datetime


class ValidationError(ValueError):
    pass


def _get(d, k, required=False, default=None):
    if d is None:
        d = {}
    v = d.get(k, default)
    if required and (v is None or v == ''):
        raise ValidationError(f'Campo requerido: {k}')
    return v


def _parse_date(s):
    if not s:
        return None
    if isinstance(s, (date, datetime)):
        return s if isinstance(s, date) else s.date()
    try:
        return datetime.fromisoformat(str(s)).date()
    except ValueError:
        raise ValidationError(f'Fecha invalida: {s}')


def parse_filters(args) -> dict:
    """Parsea query string de filtros comunes."""
    out = {}
    for key in ('channel', 'cell', 'agent_doc'):
        v = args.get(key)
        if v:
            out[key] = v.strip()
    fd = args.get('from_date') or args.get('from')
    td = args.get('to_date') or args.get('to')
    if fd:
        out['from_date'] = _parse_date(fd)
    if td:
        out['to_date'] = _parse_date(td)
    return out


def parse_audit_payload(data) -> dict:
    verdict = _get(data, 'verdict', required=True)
    return {
        'verdict': str(verdict).strip().lower(),
        'classification': (_get(data, 'classification') or None),
        'notes': (_get(data, 'notes') or None),
    }


def parse_root_cause_payload(data) -> dict:
    whys = data.get('whys') if isinstance(data, dict) else None
    if not isinstance(whys, list):
        whys = []
    whys = [str(w).strip() if w else '' for w in whys][:5]
    return {
        'whys': whys,
        'root_cause': _get(data, 'root_cause') or None,
        'action_owner_id': data.get('action_owner_id') or None,
        'due_date': _parse_date(data.get('due_date')),
        'status': (data.get('status') or 'open').strip().lower(),
    }


def parse_coaching_payload(data) -> dict:
    agent_doc = _get(data, 'agent_doc', required=True)
    sched = data.get('scheduled_at')
    sched_dt = None
    if sched:
        try:
            sched_dt = datetime.fromisoformat(str(sched))
        except ValueError:
            raise ValidationError(f'scheduled_at invalido: {sched}')
    return {
        'agent_doc': str(agent_doc).strip(),
        'agent_name': (data.get('agent_name') or None),
        'topic': (data.get('topic') or None),
        'notes': (data.get('notes') or None),
        'urgency': (data.get('urgency') or None),
        'related_survey_ids': data.get('related_survey_ids') or None,
        'scheduled_at': sched_dt,
    }

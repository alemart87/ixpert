"""Prediccion de genero a partir del nombre del cliente.

Diccionario adaptado del Iterum original (NOM_FEM / NOM_MASC) con nombres
mas comunes en Paraguay. La lista se puede ampliar via admin/UI mas adelante.
"""
import unicodedata


NOM_FEM = {
    'MARIA', 'ANA', 'LAURA', 'SARA', 'ELENA', 'ROCIO', 'BEATRIZ', 'ALICIA',
    'CLARA', 'PAULA', 'JULIA', 'NURIA', 'IRENE', 'MARTA', 'SABRINA', 'ANDREA',
    'PATRICIA', 'CLAUDIA', 'LETICIA', 'MONICA', 'VERONICA', 'GABRIELA',
    'CRISTINA', 'LILIANA', 'SILVIA', 'NORMA', 'SANDRA', 'NANCY', 'GLADYS',
    'CAROLINA', 'DANIELA', 'NATALIA', 'FLORENCIA', 'MILAGROS', 'ROXANA',
    'JESSICA', 'CYNTHIA', 'ADRIANA', 'NILDA', 'AMANDA', 'BRUNILDA', 'NADIA',
    'MABEL', 'JOHANA', 'NORA', 'YOLANDA', 'CELIA', 'IRENE', 'MIRNA',
    'VICTORIA', 'SONIA', 'EVA', 'ALBA', 'IDALINA', 'FIORELLA', 'RUTH',
    'LUISA', 'ALEXIA', 'KAREN', 'LORENA', 'CARMEN', 'MARIELA', 'ANTONIETA',
    'LUZ', 'LOURDES', 'INGRID', 'ESTHER', 'MYRIAN', 'MIRYAM', 'MIRIAM',
    'EVELIN', 'EVELYN', 'FATIMA', 'FATIMA', 'OLGA', 'OFELIA', 'TERESA',
    'JUANA', 'ROSA', 'LIDIA', 'ELISA', 'INES', 'CECILIA', 'DAISY',
    'GRACIELA', 'JUDITH', 'JOAQUINA', 'MARLENE', 'CONCEPCION',
    'ROSARIO', 'DOLORES', 'PILAR', 'SOLEDAD', 'DOMINGA', 'GUADALUPE',
    'ROCIO', 'MICAELA', 'VALERIA', 'CAMILA', 'LUCIA', 'AGUSTINA',
    'BELEN', 'TAMARA', 'GISELLE', 'CARLA', 'VANESA', 'VANESSA',
    'YESICA', 'YESSICA', 'TANIA', 'DIANA',
}

NOM_MASC = {
    'JUAN', 'JOSE', 'LUIS', 'CARLOS', 'JORGE', 'RAUL', 'PEDRO', 'DIEGO',
    'HUGO', 'ALEX', 'RENE', 'DAVID', 'ANGEL', 'JAVIER', 'SANTIAGO',
    'ANDRES', 'MATIAS', 'LUCAS', 'NICOLAS', 'JONAS', 'ALEXIS', 'JOSUE',
    'FRANCISCO', 'ANTONIO', 'MANUEL', 'GUILLERMO', 'FERNANDO', 'ROBERTO',
    'DANIEL', 'ALEJANDRO', 'RICARDO', 'ENRIQUE', 'PABLO', 'RUBEN', 'SERGIO',
    'MARCELO', 'CLAUDIO', 'OSCAR', 'WALTER', 'HECTOR', 'RAMON', 'RODRIGO',
    'GIOVANNI', 'PAULO', 'CRISTIAN', 'MARCO', 'ESTIBER', 'MARTIN',
    'MAXIMILIANO', 'JUSTO', 'EDGAR', 'MIGUEL', 'WERNER', 'APARECIDO',
    'RAFAEL', 'DENNIS', 'JULIO', 'JEAN', 'LISANDRO', 'RICHARD', 'CAYO',
    'CHRISTIAN', 'ADRIAN', 'ALBERTO', 'VALDOVINO', 'MILTON', 'MILNER',
    'OSVALDO', 'CRISTHIAN', 'KELLWIN', 'MARCOS', 'PASCUAL',
    'GERARDO', 'EMANUEL', 'EMMANUEL', 'AGUSTIN', 'MAURICIO', 'CESAR',
    'GUSTAVO', 'JESUS', 'JONATHAN', 'JONATAN', 'BRUNO', 'ARIEL',
    'OMAR', 'NESTOR', 'IVAN', 'PATRICIO', 'EZEQUIEL', 'JOAQUIN',
    'TOMAS', 'BENJAMIN', 'GABRIEL', 'MAXIMO', 'RODRIGO', 'GONZALO',
    'EMILIANO', 'ESTEBAN', 'FELIX', 'GERMAN', 'LEANDRO', 'LEONARDO',
    'NAHUEL', 'SEBASTIAN', 'SILVIO', 'VICTOR', 'WILSON', 'ARMANDO',
    'EVER', 'FREDDY', 'IGNACIO', 'JAIME', 'JULIAN', 'LEOPOLDO',
    'OLIVER', 'RODOLFO', 'ROGELIO', 'SAMUEL', 'TADEO', 'WILFRIDO',
    'BLAS', 'CRISTOBAL', 'EUSEBIO', 'FELICIANO', 'HORACIO', 'JOAO',
    'LADISLAO', 'MOISES', 'ORLANDO', 'PORFIRIO', 'ROQUE',
    'SEBASTIAN', 'VICENTE', 'CRISTHIAN', 'DENIS', 'EDWIN', 'EVERSON',
    'ROCIO',  # Rocío en Paraguay mayormente femenino — corregir si fuese
}

# Si un nombre aparece en ambos, gana el contexto local. En Paraguay
# "ROCIO" es predominantemente femenino, lo movemos solo a NOM_FEM:
NOM_MASC.discard('ROCIO')


def _strip_accents(s: str) -> str:
    s = unicodedata.normalize('NFD', s)
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn')


def predict_gender(full_name: str | None) -> tuple[str, str | None]:
    """Devuelve (genero, primer_nombre_no_detectado).

    genero: 'Femenino' | 'Masculino' | 'No Detectado'
    Si no detecto el genero, el segundo valor es el primer nombre limpio
    (para que el supervisor lo agregue al diccionario).
    """
    if not full_name:
        return ('No Detectado', None)
    parts = _strip_accents(str(full_name)).upper().split()
    if not parts:
        return ('No Detectado', None)
    first = parts[0]
    if first in NOM_FEM:
        return ('Femenino', None)
    if first in NOM_MASC:
        return ('Masculino', None)
    # Heuristica: terminaciones tipicas en castellano
    if first.endswith('A') and len(first) >= 3:
        return ('Femenino', first)
    if first.endswith('O') and len(first) >= 3:
        return ('Masculino', first)
    return ('No Detectado', first)

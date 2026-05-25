"""Tests de prediccion de genero."""
from iterum.services.gender import predict_gender


def test_predict_female_from_dict():
    g, hint = predict_gender('MARIA JOSE GONZALEZ')
    assert g == 'Femenino'
    assert hint is None


def test_predict_male_from_dict():
    g, hint = predict_gender('CARLOS ALBERTO LOPEZ')
    assert g == 'Masculino'
    assert hint is None


def test_predict_with_accents():
    g, _ = predict_gender('JOSÉ MARÍA')
    assert g == 'Masculino'


def test_unknown_returns_hint():
    g, hint = predict_gender('XKAZBLQX SOMEONE')
    assert g == 'No Detectado'
    assert hint == 'XKAZBLQX'


def test_heuristic_a_ending():
    g, _ = predict_gender('SOMENAMEA')
    assert g == 'Femenino'


def test_heuristic_o_ending():
    g, _ = predict_gender('SOMENAMEO')
    assert g == 'Masculino'


def test_empty():
    g, hint = predict_gender(None)
    assert g == 'No Detectado'
    assert hint is None

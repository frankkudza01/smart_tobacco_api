from apps.ai_intelligence.local_models.ridge_yield import (
    collect_org_yield_training_rows,
    fit_ridge_yield,
    predict_yield_kg,
)


def test_fit_ridge_yield_minimum_samples():
    samples = [([1.0, float(i * 10), 2.0], float(100 + i * 5)) for i in range(4)]
    assert fit_ridge_yield(samples) is None


def test_fit_ridge_yield_predicts():
    samples = [([1.0, float(400 + i * 10), 2.0], float(500 + i * 20)) for i in range(6)]
    fit = fit_ridge_yield(samples, ridge_lambda=5.0)
    assert fit is not None
    pred = predict_yield_kg(fit, 420.0, 2.0)
    assert 400 < pred < 700


@pytest.mark.django_db
def test_collect_org_rows_empty():
    from apps.organizations.models import Organization

    org = Organization.objects.create(name="O-ridge-collect-empty-test")
    assert collect_org_yield_training_rows(org) == []

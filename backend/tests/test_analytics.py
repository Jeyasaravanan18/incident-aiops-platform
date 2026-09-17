from app.api.v1.analytics import calculate_percentile
from app.schemas.analytics import MTTAMetric, MTTRMetric


def test_percentile_calculation() -> None:
    # Empty list
    assert calculate_percentile([], 0.5) == 0.0

    # Odd length list: [10, 20, 30]
    values = [10.0, 20.0, 30.0]
    assert calculate_percentile(values, 0.5) == 20.0

    # Even length list: [10, 20, 30, 40]
    values = [10.0, 20.0, 30.0, 40.0]
    assert calculate_percentile(values, 0.5) == 25.0

    # P95 calculation
    values = [float(i) for i in range(1, 101)]  # 1 to 100
    p95 = calculate_percentile(values, 0.95)
    assert 94.0 <= p95 <= 96.0


def test_mtta_definition_and_structure() -> None:
    mtta = MTTAMetric(mean_minutes=4.5, count=12)
    assert mtta.mean_minutes == 4.5
    assert mtta.count == 12
    assert "acknowledged_at - detected_at" in mtta.definition


def test_mttr_definition_and_structure() -> None:
    mttr = MTTRMetric(
        mean_minutes=35.2,
        median_minutes=28.0,
        p95_minutes=72.5,
        count=8,
    )
    assert mttr.mean_minutes == 35.2
    assert mttr.median_minutes == 28.0
    assert mttr.p95_minutes == 72.5
    assert mttr.count == 8
    assert "resolved_at - detected_at" in mttr.definition

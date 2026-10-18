from carreport import format_report

CAR = {"id": 1, "make": "Volvo", "model": "V70", "year": 2015, "mileage": 120000}


def test_report_lists_valuations():
    valuations = [
        {"timestamp": "2026-10-18T12:00:00Z", "price": 85000, "comment": "Good condition"},
    ]
    report = format_report(CAR, valuations)
    assert "Volvo V70 (2015), 120000 km" in report
    assert "85000 DKK" in report
    assert "Good condition" in report


def test_report_without_valuations():
    assert "No valuations yet." in format_report(CAR, [])

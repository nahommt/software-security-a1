__version__ = "0.1.0"


def format_report(car, valuations):
    lines = [
        f"Valuation report for car {car['id']}",
        f"{car['make']} {car['model']} ({car['year']}), {car['mileage']} km",
        "",
    ]
    if not valuations:
        lines.append("No valuations yet.")
    for valuation in valuations:
        lines.append(
            f"{valuation['timestamp']}  {valuation['price']} DKK  {valuation['comment']}"
        )
    return "\n".join(lines) + "\n"

# Office App

from genro_routes import RoutingClass, Router, route


class OfficeApp(RoutingClass):
    """Office application."""

    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def documents(self):
        return {"documents": ["report.pdf", "invoice.xlsx"]}

    @route("api")
    def calendar(self):
        return {"events": ["meeting 10:00", "call 14:00"]}

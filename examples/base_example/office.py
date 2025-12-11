# Office App

from genro_routes import RoutedClass, route


class OfficeApp(RoutedClass):
    """Office application."""

    @route("api")
    def documents(self):
        return {"documents": ["report.pdf", "invoice.xlsx"]}

    @route("api")
    def calendar(self):
        return {"events": ["meeting 10:00", "call 14:00"]}

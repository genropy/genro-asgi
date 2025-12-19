# Shop App

from genro_routes import RoutingClass, Router, route


class ShopApp(RoutingClass):
    """Shop application."""

    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def products(self):
        return {"products": ["laptop", "phone", "tablet"]}

    @route("api")
    def cart(self):
        return {"items": [], "total": 0}

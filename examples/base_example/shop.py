# Shop App

from genro_routes import RoutedClass, route


class ShopApp(RoutedClass):
    """Shop application."""

    @route("api")
    def products(self):
        return {"products": ["laptop", "phone", "tablet"]}

    @route("api")
    def cart(self):
        return {"items": [], "total": 0}

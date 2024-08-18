from lib.destinations.destination import Destination

class ExampleDestination(Destination):
    """
    Example destination for uploading data.
    """
    def __init__(self):
        super().__init__("Example")

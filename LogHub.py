class LogHub:

    def __init__(self, name: str, position: (int,int), transmissionRange: float, image: str):
        self.name = name
        self.positionX = position[0]
        self.positionY = position[1]
        self.transmissionRange = transmissionRange
        self.image = image



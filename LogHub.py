class GroundStructure:
    nextId = 0

    def __init__(self, name: str, position: (int,int), image: str, player: int):
        self.id = 10000 + GroundStructure.nextId
        GroundStructure.nextId += 1
        self.name = name
        self.positionX = position[0]
        self.positionY = position[1]
        self.image = image
        self.player = player

class LogHub(GroundStructure):

    def __init__(self, name: str, position: (int,int), image: str, player: int, transmissionRange: int):
        super().__init__(name, position, image, player)
        self.transmissionRange = transmissionRange

class GroundRetransmitter(GroundStructure):

    def __init__(self, name: str, position: (int,int), image: str, player: int, transmissionRange: int, parent_base_id: int):
        super().__init__(name, position, image, player)
        self.transmissionRange = transmissionRange
        self.parent_base_id = parent_base_id

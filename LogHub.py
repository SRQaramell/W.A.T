from enum import Enum

class SupplyType(Enum):
    AAMunition = 1
    Fuel = 2
    Food = 3
    Munition = 4
    Explosives = 5
    MedicalSupplies = 6
    Gruz200 = 7
    Gruz300 = 8
    SpareParts = 9
    Other = 10

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

    def __init__(self, name: str, position: (int,int), image: str, player: int,
                 transmissionRange: int,
                 max_retransmitters: int = 3,
                 max_uavs: int = 5,
                 max_air_retransmitters: int = 2,
                 viewRange: int = 100,
                 storage: dict | None = None):  # NEW
        super().__init__(name, position, image, player)
        self.transmissionRange = transmissionRange
        self.available_retransmitters = max_retransmitters
        self.max_deployed_uavs = max_uavs
        self.current_spawned_uavs = 0
        self.viewRange = viewRange

        # NEW: airborne (UAV) retransmitters
        self.max_air_retransmitters = max_air_retransmitters
        self.current_air_retransmitters = 0

        self.inStorage = dict(storage) if storage is not None else {}
        self.max_supply_trucks = 2
        self.current_supply_trucks = 0


class GroundRetransmitter(GroundStructure):

    def __init__(self, name: str, position: (int,int), image: str, player: int, transmissionRange: int, parent_base_id: int):
        super().__init__(name, position, image, player)
        self.transmissionRange = transmissionRange
        self.parent_base_id = parent_base_id

class ElectronicWarfare(GroundStructure):

    def __init__(self, name: str, position: (int,int), image: str, player: int, jammingRange: int, jammingFreq: list):
        super().__init__(name, position, image, player)
        self.jammingRange = jammingRange
        self.jammingFreq = jammingFreq


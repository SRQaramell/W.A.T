import UAVUnits
from LogHub import SupplyType

class GroundUnit(UAVUnits.Unit):

    def __init__(self, name: str, chanceToHit: int, baseSpeed: float, state: UAVUnits.UnitState, position: (int,int), image: str, armourType: UAVUnits.ArmourType, player: int):
        super().__init__(name, chanceToHit, baseSpeed, state, position, image, armourType, player)

class SupplyVehicle(GroundUnit):

    def __init__(self,name: str, chanceToHit: int, baseSpeed: float, state: UAVUnits.UnitState, position: (int,int), image: str, armourType: UAVUnits.ArmourType, player: int, cargoType: SupplyType, cargoAmmount: int):
        super().__init__(name, chanceToHit, baseSpeed, state, position, image, armourType, player)
        self.cargoType = cargoType
        self.cargoAmmount = cargoAmmount

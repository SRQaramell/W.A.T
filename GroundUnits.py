from Scripts.mavgraph import field_types

import UAVUnits
from LogHub import SupplyType

class GroundUnit(UAVUnits.Unit):

    def __init__(self, name: str, chanceToHit: int, baseSpeed: float, state: UAVUnits.UnitState, position: (int,int), image: str, armourType: UAVUnits.ArmourType, player: int):
        super().__init__(name, chanceToHit, baseSpeed, state, position, image, armourType, player)

class SupplyVehicle(GroundUnit):

    def __init__(self,name: str, chanceToHit: int, baseSpeed: float, state: UAVUnits.UnitState, position: (int,int), image: str, armourType: UAVUnits.ArmourType, player: int, cargoType: SupplyType, cargoAmmount: int, target_unit_id: int, home_base_id: int):
        super().__init__(name, chanceToHit, baseSpeed, state, position, image, armourType, player)
        self.cargoType = cargoType
        self.cargoAmmount = cargoAmmount
        self.target_unit_id = target_unit_id   # where to deliver
        self.home_base_id = home_base_id       # where to go back
        self.phase = "to_target"

class CombatVehicle(GroundUnit):

    def __init__(self,name: str, chanceToHit: int, baseSpeed: float, state: UAVUnits.UnitState, position: (int,int), image: str, armourType: UAVUnits.ArmourType, player: int):
        super().__init__(name, chanceToHit, baseSpeed, state, position, image, armourType, player)


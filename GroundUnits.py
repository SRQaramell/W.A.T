import UAVUnits

class GroundUnit(UAVUnits.Unit):

    def __init__(self, name: str, chanceToHit: int, baseSpeed: float, state: UAVUnits.UnitState, position: (int,int), image: str, armourType: UAVUnits.ArmourType, player: int):
        super().__init__(name, chanceToHit, baseSpeed, state, position, image, armourType, player)


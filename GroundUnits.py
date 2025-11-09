# GroundUnits.py
import UAVUnits
from LogHub import SupplyType

class GroundUnit(UAVUnits.Unit):
    def __init__(self,
                 name: str,
                 chanceToHit: int,
                 baseSpeed: float,
                 state: UAVUnits.UnitState,
                 position: (int, int),
                 image: str,
                 armourType: UAVUnits.ArmourType,
                 player: int,
                 max_fuel: float = 0.0,
                 fuel_consumption_per_tick: float = 0.0):
        super().__init__(name, chanceToHit, baseSpeed, state, position, image, armourType, player)
        # fuel-related
        self.maxFuel = max_fuel
        self.currentFuel = max_fuel
        self.fuelConsumptionPerTick = fuel_consumption_per_tick

    def tick_unit(self, dt: float):
        # if we’re supposed to move, we must have fuel
        if self.state == UAVUnits.UnitState.Moving:
            if self.currentFuel <= 0:
                # out of fuel – stop right here
                self.state = UAVUnits.UnitState.Idle
                return
            # burn (per tick, not per dt — your loop is fixed-step)
            self.currentFuel -= self.fuelConsumptionPerTick
            if self.currentFuel < 0:
                self.currentFuel = 0
        # normal movement
        super().tick_unit(dt)


class SupplyVehicle(GroundUnit):
    def __init__(self,
                 name: str,
                 chanceToHit: int,
                 baseSpeed: float,
                 state: UAVUnits.UnitState,
                 position: (int, int),
                 image: str,
                 armourType: UAVUnits.ArmourType,
                 player: int,
                 cargoType: SupplyType,
                 cargoAmmount: int,
                 target_unit_id: int,
                 home_base_id: int,
                 max_fuel: float = 0.0,
                 fuel_consumption_per_tick: float = 0.0):
        super().__init__(name, chanceToHit, baseSpeed, state, position, image, armourType, player,
                         max_fuel=max_fuel,
                         fuel_consumption_per_tick=fuel_consumption_per_tick)
        self.cargoType = cargoType
        self.cargoAmmount = cargoAmmount
        self.target_unit_id = target_unit_id   # where to deliver
        self.home_base_id = home_base_id       # where to go back
        self.phase = "to_target"


class CombatVehicle(GroundUnit):
    def __init__(self,
                 name: str,
                 chanceToHit: int,
                 baseSpeed: float,
                 state: UAVUnits.UnitState,
                 position: (int, int),
                 image: str,
                 armourType: UAVUnits.ArmourType,
                 player: int,
                 max_fuel: float = 0.0,
                 fuel_consumption_per_tick: float = 0.0):
        super().__init__(name, chanceToHit, baseSpeed, state, position, image, armourType, player,
                         max_fuel=max_fuel,
                         fuel_consumption_per_tick=fuel_consumption_per_tick)


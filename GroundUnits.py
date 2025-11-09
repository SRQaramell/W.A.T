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
        # fuel gate for movement
        if self.state == UAVUnits.UnitState.Moving:
            if self.currentFuel <= 0:
                self.state = UAVUnits.UnitState.Idle
                return
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
                 shooting_range: float,
                 ammo_type: SupplyType,
                 ammo_count: int,
                 max_fuel: float = 0.0,
                 fuel_consumption_per_tick: float = 0.0):
        super().__init__(name, chanceToHit, baseSpeed, state, position, image, armourType, player,
                         max_fuel=max_fuel,
                         fuel_consumption_per_tick=fuel_consumption_per_tick)
        # NEW combat stuff
        self.shootingRange = shooting_range
        self.ammoType = ammo_type
        self.ammoCount = ammo_count

    def can_shoot(self):
        return self.ammoCount > 0

    def shoot(self, target):
        """
        Placeholder – same idea as AA: check distance, reduce ammo.
        You can later hook it into your game loop like AA units.
        """
        if self.ammoCount <= 0:
            return False
        # very simple distance check
        dx = target.positionX - self.positionX
        dy = target.positionY - self.positionY
        dist2 = dx * dx + dy * dy
        if dist2 <= self.shootingRange * self.shootingRange:
            self.ammoCount -= 1
            return True
        return False


class Tank(CombatVehicle):
    def __init__(self,
                 name: str,
                 state: UAVUnits.UnitState,
                 position: (int, int),
                 image: str,
                 player: int,
                 max_fuel: float):
        # sensible defaults for a tank
        super().__init__(
            name=name,
            chanceToHit=60,                  # tweak
            baseSpeed=3,                     # slower than truck
            state=state,
            position=position,
            image=image,
            armourType=UAVUnits.ArmourType.HeavyArmour,
            player=player,
            shooting_range=200.0,            # tank gun range in your world units
            ammo_type=SupplyType.TanksShells,
            ammo_count=20,
            max_fuel=max_fuel,
            fuel_consumption_per_tick=0.08
        )

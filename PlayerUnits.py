import random
from enum import Enum
import math

# Explosive vs Armour table

#       HE_FRAG,    HEAT,   FAE
# Heavy -80        20       -90
# Light -10        -30      -20
# None  30         30       40
# Inf   50         -10      60
ExplosiveArmourTable = [[-80,20,-90],
                        [-10,-30,-20],
                        [30,30,40],
                        [50,-10,60]]
class UnitState(Enum):
    Idle = 1
    Destroyed = 2
    Damaged = 3
    Moving = 4
    Landed = 5

class ExplosiveType(Enum):
    HE_FRAG = 0
    HEAT = 1
    FAE = 2

class ArmourType(Enum):
    HeavyArmour = 0
    LightArmour = 1
    Unarmored = 2
    Infantry = 3

class Unit:
    nextID = 0
    positionX = 0
    poistionY = 0

    def __init__(self, name: str, chanceToHit: int, baseSpeed: float, state: UnitState, position: (int,int), image: str, armourType: ArmourType):
        self.name = name
        self.chanceToHit = chanceToHit
        self.baseSpeed = baseSpeed
        self.state = state
        self.id = Unit.nextID
        Unit.nextID += 1
        self.positionX = position[0]
        self.positionY = position[1]
        self.image = image
        self.armourType = armourType

    def tick_unit(self, destination: (int,int), dt: float):
        if self.state != UnitState.Moving:
            return

        targetX = destination[0]
        targetY = destination[1]

        destinationX = targetX - self.positionX
        destinationY = targetY - self.poistionY

        dist = math.hypot(destinationX, destinationY)

        if dist == 0:
            self.state = UnitState.Idle
            return
        effectiveSpeed = self.baseSpeed * getModifiersAtPos(destinationX, destinationY)

        maxStep = effectiveSpeed * dt

        if maxStep >= dist:
            self.positionX = targetX
            self.positionY = targetY
            self.state = UnitState.Idle
        else:
            self.positionX = destinationX/dist * maxStep
            self.positionY = destinationY/dist * maxStep

    def __str__(self):
        return f"{self.nazwa})"

class UAV(Unit):
    currentBattery = 100.0

    def __init__(self, currentWeight: float, idleBatteryDrainPerTick: float, moveBatteryDrainPerTick: float):
        super()
        self.currentWeight = currentWeight
        self.idleBatteryDrainPerTick = idleBatteryDrainPerTick
        self.moveBatteryDrainPerTick = moveBatteryDrainPerTick

    def tick_unit(self, destination: (int,int), dt: float):
        super().tick_unit(destination, dt)
        self.currentBattery -= self.getCurrentBatteryDrainPerTick()
        if self.currentBattery <= 0.0:
            self.state = UnitState.Destroyed
            return

    def getCurrentBatteryDrainPerTick(self):
        if self.state == UnitState.Idle:
            return self.idleBatteryDrainPerTick * getWindModifiers(self.positionX, self.positionY)
        if self.state == UnitState.Moving:
            return self.moveBatteryDrainPerTick * getWindModifiers(self.positionX, self.positionY)

class LoiteringMunition(UAV):

    def __init__(self, payload: float, explosiveType: ExplosiveType):
        super()
        self.payload = payload
        self.explosiveType = explosiveType

    def attack(self, target: Unit):


def calculateChanceToDestroy(attacker: LoiteringMunition, attacked: Unit):
        return ExplosiveArmourTable[attacked.armourType.value][attacker.explosiveType.value]

def isHit(attacker: LoiteringMunition, attacked: Unit):
    calculated = random.randint(1,100)
    if calculated <= attacker.chanceToHit + calculateChanceToDestroy(attacker, attacked):
        attacked.state = UnitState.Destroyed
    attacker.state = UnitState.Destroyed
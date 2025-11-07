import random
from enum import Enum

from UAVUnits import Unit, UAV, UnitState

class AAStatus(Enum):
    Idle = 1
    Aiming = 2
    Firing = 3
    OutOfAmmo = 4

class AntiAir(Unit):
    currentAimTime = 0.0

    def __init__(self, range: float, ammoCount: int, aimTime: float, timeBetweenShots: float, AAstate: AAStatus):
        self.range = range
        self.ammoCount = ammoCount
        self.aimTime = aimTime
        self.timeBetweenShots = timeBetweenShots
        self.AAstate = AAstate

    def tickAA(self, dt: float, target: UAV):
        if self.AAstate == AAStatus.Idle:
            return
        if self.AAstate == AAStatus.Aiming and target is not None:
            if self.currentAimTime < self.aimTime:
                self.currentAimTime += dt
            else:
                self.AAstate = AAStatus.Firing

        if self.AAstate == AAStatus.Firing and target is not None:
            self.hitCheck(target)
            self.currentAimTime = 0.0
            self.ammoCount -= 1
            if target.state == UnitState.Destroyed:
                target = None
                self.AAstate = AAStatus.Idle
                return
            self.AAstate = AAStatus.Aiming



    def hitCheck(self, target: UAV):
        calculated = random.randint(1,100)
        if calculated < self.chanceToHit + getTerrainHitModifiers + getUAVHitModifiers:
            target.state = UnitState.Destroyed
        return
import math
import random
from enum import Enum

from UAVUnits import Unit, UAV, UnitState, ArmourType

class AAStatus(Enum):
    Idle = 1
    Aiming = 2
    Firing = 3
    OutOfAmmo = 4

class AntiAir(Unit):
    currentAimTime = 0.0
    target = None

    def __init__(self, name: str, chanceToHit: int, baseSpeed: float, state: UnitState, position: (int,int), image: str, armourType: ArmourType, player: int ,range: float, ammoCount: int, aimTime: float, timeBetweenShots: float, AAstate: AAStatus):
        super().__init__(name, chanceToHit, baseSpeed, state, position, image, armourType,player)
        self.range = range
        self.ammoCount = ammoCount
        self.aimTime = aimTime
        self.timeBetweenShots = timeBetweenShots
        self.AAstate = AAstate

    def tickAA(self, dt: float, units):
        if self.ammoCount <= 0:
            self.AAstate = AAStatus.OutOfAmmo
            return
        if self.AAstate == AAStatus.Idle:
            targets = self.scanForTarget(units)
            if len(targets) > 0:
                self.target = targets[0]
                self.AAstate = AAStatus.Aiming
        if self.AAstate == AAStatus.Aiming and self.target is not None:
            if self.currentAimTime < self.aimTime:
                self.currentAimTime += dt
            else:
                self.AAstate = AAStatus.Firing

        if self.AAstate == AAStatus.Firing and self.target is not None:
            self.hitCheck(self.target)
            self.currentAimTime = 0.0
            self.ammoCount -= 1
            if self.target.state == UnitState.Destroyed:
                self.target = None
                self.AAstate = AAStatus.Idle
                return
            self.AAstate = AAStatus.Aiming

    def hitCheck(self, target: UAV):
        calculated = random.randint(1,100)
        if calculated < self.chanceToHit: #+ getTerrainHitModifiers + getUAVHitModifiers:
            target.state = UnitState.Destroyed
        return

    def scanForTarget(self, targetList):
        if self.AAstate != AAStatus.Idle:
            return

        inRange = []
        for u in targetList:
            if u is self:
                continue
            if u.player == self.player:
                continue

            dx = u.positionX - self.positionX
            dy = u.positionY - self.positionY
            distance = math.sqrt(dx * dx + dy * dy)

            if distance <= self.range:
                inRange.append(u)


        return inRange
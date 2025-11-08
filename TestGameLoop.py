import threading
import time
import math

from flask import Flask, request, send_file, render_template_string, jsonify
from io import BytesIO
from PIL import Image, ImageDraw
import UAVUnits, AntiAirUnits, LogHub
from UAVUnits import UnitState

app = Flask(__name__)

MAP_WIDTH = 800
MAP_HEIGHT = 500
TICK_RATE = 10
PLAYER1 = 1
ATTACK_RANGE = 3

# --- HTML PAGE ---
PAGE_TMPL = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Unit Map with Info Panel</title>
  <style>
    body {
      margin: 0;
      display: flex;
      height: 100vh;
      overflow: hidden;
    }
    #canvas {
      flex: 1 1 auto;
      background: #f0f0f0;
      display: block;
    }
    #infoPanel {
      width: 300px;
      padding: 10px;
      background: #fff;
      border-left: 1px solid #ccc;
      overflow-y: auto;
      font-family: sans-serif;
    }
    #infoPanel h2 {
      margin-top: 0;
    }
    #infoPanel ul {
      list-style: none;
      padding-left: 0;
    }
    #infoPanel li {
      margin-bottom: 4px;
    }
  </style>
</head>
<body>
  <canvas id="canvas" width="800" height="600"></canvas>
  <div id="infoPanel">
    <h2>Selected Unit Info</h2>
    <div id="unitInfo">No unit selected.</div>
  </div>

  <script>
    const canvas = document.getElementById("canvas");
    const ctx = canvas.getContext("2d");
    const infoPanel = document.getElementById("unitInfo");

    let placeRetransmitterMode = false;
    let placingBaseId = null;
    let placingBaseData = null;

    let units = [];             // will be fetched from server
    let selectedUnitId = null;
    let selectedUnitSnapshot = null;
    let moveTarget = null;      // { x:…, y:… } or null

    function startRetransmitterPlacing(baseId, baseData) {
      placeRetransmitterMode = true;
      placingBaseId = baseId;
      placingBaseData = baseData;
    }

    function makeUnitSnapshot(u) {
      const snap = {
        id: u.id,
        name: u.name,
        unit_class: u.unit_class,
        player: u.player,
        transmissionRange: u.transmissionRange,
        x: u.x,
        y: u.y
      };
    
      // bases (LogHub) have this and we want panel to refresh when it changes
      if (u.unit_class === "LogHub") {
        snap.available_retransmitters = u.available_retransmitters;
      }
    
      return snap;
    }
    
    function isSameUnitSnapshot(a, b) {
      let same =
        a.id === b.id &&
        a.name === b.name &&
        a.unit_class === b.unit_class &&
        a.player === b.player &&
        a.transmissionRange === b.transmissionRange &&
        a.x === b.x &&
        a.y === b.y;
    
      // for bases, also check available_retransmitters
      if (a.unit_class === "LogHub") {
        same = same && a.available_retransmitters === b.available_retransmitters;
      }
    
      return same;
    }


    function fetchUnits() {
      fetch("/units")
        .then(res => res.json())
        .then(data => {
          units = data;
    
          // recreate images
          units.forEach(u => {
            const img = new Image();
            img.src = u.image;
            u._img = img;
          });
    
          if (selectedUnitId !== null) {
            const selected = units.find(u => u.id === selectedUnitId);
            if (selected) {
              if (!selectedUnitSnapshot || !isSameUnitSnapshot(selectedUnitSnapshot, selected)) {
                updateInfoPanel(selected);
                // store fresh snapshot (only fields we care about)
                selectedUnitSnapshot = makeUnitSnapshot(selected);
              }
            } else {
              // selected unit disappeared
              infoPanel.innerHTML = "No unit selected.";
              selectedUnitId = null;
              selectedUnitSnapshot = null;
            }
          }
          return units;
        })
        .catch(err => console.error("Failed to fetch units:", err));
    }

        canvas.addEventListener("click", (event) => {
          const rect = canvas.getBoundingClientRect();
          const scaleX = canvas.width / rect.width;
          const scaleY = canvas.height / rect.height;
        
          const clickX = (event.clientX - rect.left) * scaleX;
          const clickY = (event.clientY - rect.top)  * scaleY;

          // 0. placing retransmitter?
          if (placeRetransmitterMode && placingBaseId !== null) {
            // optional client-side check to give faster feedback
            if (placingBaseData && placingBaseData.transmissionRange) {
              const dx = clickX - placingBaseData.x;
              const dy = clickY - placingBaseData.y;
              const dist = Math.sqrt(dx*dx + dy*dy);
              if (dist > placingBaseData.transmissionRange) {
                alert("Spot outside base transmission range");
                return;
              }
            }
        
            fetch("/place_retransmitter", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                base_id: placingBaseId,
                x: clickX,
                y: clickY
              })
            })
            .then(res => res.json())
            .then(d => {
              if (d.status === "ok") {
                placeRetransmitterMode = false;
                const baseId = placingBaseId;
                placingBaseId = null;
                placingBaseData = null;
                fetchUnits().then((unitsNow) => {
                    const baseNow = units.find(u => u.id === baseId);
                    if (baseNow) {
                        updateInfoPanel(baseNow);
                        // keep snapshot in sync if you use snapshot logic
                        selectedUnitSnapshot = makeUnitSnapshot(baseNow);
                    }
                });
                // try to uncheck the box if the same base is still shown
                const chk = document.getElementById("placeRtChk");
                const hint = document.getElementById("placeHint");
                if (chk) chk.checked = false;
                if (hint) hint.textContent = "";
              } else {
                alert(d.message || "Error placing retransmitter");
              }
            })
            .catch(err => console.error(err));
        
            return; // stop normal click handling
          }
        
          // 1. did we click on a unit?
          let clickedUnit = null;
          for (const u of units) {
            const size = u.size || 24;
            const half = size / 2;
            if (clickX >= u.x - half && clickX <= u.x + half &&
                clickY >= u.y - half && clickY <= u.y + half) {
              clickedUnit = u;
              break;
            }
          }
        
          // we have a selected unit already?
          const selected = selectedUnitId !== null
              ? units.find(u => u.id === selectedUnitId)
              : null;
        
          // 2. Ctrl+click on enemy unit -> attack (only if selected is LoiteringMunition)
          if (clickedUnit && event.ctrlKey && selected &&
              selected.unit_class === "LoiteringMunition" &&
              clickedUnit.player !== selected.player) {
        
            fetch("/attack_unit", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                attacker_id: selected.id,
                target_id: clickedUnit.id
              })
            })
            .then(res => res.json())
            .then(d => {
              // refresh after attack
              fetchUnits();
            })
            .catch(err => console.error(err));
        
            return; // stop here – attack handled
          }
        
          // 3. if we clicked a unit (no ctrl or not enemy / not LM) -> just select it
          if (clickedUnit) {
            selectedUnitId = clickedUnit.id;
            moveTarget = null;
            updateInfoPanel(clickedUnit);
            return;
          }
        
          // 4. click on empty ground -> move (only if something selected)
          if (selectedUnitId !== null) {
            fetch("/move_unit", {
              method: "POST",
              headers:  { "Content-Type": "application/json" },
              body: JSON.stringify({ id: selectedUnitId, x: clickX, y: clickY })
            })
            .then(res => res.json())
            .then(data => {
              fetchUnits();
            })
            .catch(err => console.error(err));
            moveTarget = { x: clickX, y: clickY };
          }
        });


    function updateInfoPanel(u) {
      const isBase = u.unit_class === "LogHub";
      const wasPlacingThisBase =
        placeRetransmitterMode && placingBaseId === u.id;
    
      let html = "<ul>";
      for (const key in u) {
        if (u.hasOwnProperty(key) && key !== "_img") {
          html += `<li><strong>${key}:</strong> ${u[key]}</li>`;
        }
      }
      html += "</ul>";
    
      if (isBase) {
        html += `<button id="placeRtBtn">Place retransmitter</button>`;
        if (wasPlacingThisBase) {
          html += `<p id="placeMsg">Click on the map inside the base range to place retransmitter…</p>`;
        }
      }
    
      infoPanel.innerHTML = html;
    
      if (isBase) {
        const btn = document.getElementById("placeRtBtn");
        btn.addEventListener("click", () => {
          startRetransmitterPlacing(u.id, u);
          // show message without re-rendering whole panel
          const p = document.getElementById("placeMsg");
          if (p) {
            p.textContent = "Click on the map inside the base range to place retransmitter…";
          } else {
            infoPanel.innerHTML += `<p id="placeMsg">Click on the map inside the base range to place retransmitter…</p>`;
          }
        });
      }
    }



        function drawUnits() {
          ctx.clearRect(0, 0, canvas.width, canvas.height);
        
          for (const u of units) {
            const size = u.size || 24;
            const half = size / 2;
        
            // 1) draw range for AntiAir
            if (u.unit_class === "AntiAir" && u.range) {
              ctx.beginPath();
              ctx.arc(u.x, u.y, u.range, 0, Math.PI * 2);
              ctx.strokeStyle = "rgba(0, 128, 255, 0.6)";
              ctx.lineWidth = 2;
              ctx.stroke();
              ctx.fillStyle = "rgba(0, 128, 255, 0.08)";
              ctx.fill();
            }
        
            // 2) draw transmission range for LogHub (bases)
            if (u.unit_class === "LogHub" && u.transmissionRange) {
              ctx.beginPath();
              ctx.arc(u.x, u.y, u.transmissionRange, 0, Math.PI * 2);
              ctx.strokeStyle = "rgba(0, 200, 0, 0.6)";   // green-ish for comms
              ctx.lineWidth = 2;
              ctx.stroke();
              ctx.fillStyle = "rgba(0, 200, 0, 0.05)";
              ctx.fill();
            }
        
            // 3) draw transmission range for GroundRetransmitter
            if (u.unit_class === "GroundRetransmitter" && u.transmissionRange) {
              ctx.beginPath();
              ctx.arc(u.x, u.y, u.transmissionRange, 0, Math.PI * 2);
              ctx.strokeStyle = "rgba(255, 165, 0, 0.6)";  // orange-ish
              ctx.lineWidth = 2;
              ctx.stroke();
              ctx.fillStyle = "rgba(255, 165, 0, 0.05)";
              ctx.fill();
            }
        
            // draw unit/base icon
            const img = u._img;
            if (img && img.complete) {
              ctx.drawImage(img, u.x - half, u.y - half, size, size);
        
              // tint only real units (optional — bases could stay untinted)
              ctx.save();
              ctx.globalAlpha = 0.35;
              if (u.player === 1) ctx.fillStyle = "blue";
              else if (u.player === 2) ctx.fillStyle = "red";
              else ctx.fillStyle = "gray";
              ctx.fillRect(u.x - half, u.y - half, size, size);
              ctx.restore();
            } else {
              ctx.beginPath();
              ctx.arc(u.x, u.y, half, 0, Math.PI * 2);
              if (u.player === 1) ctx.fillStyle = "blue";
              else if (u.player === 2) ctx.fillStyle = "red";
              else ctx.fillStyle = "gray";
              ctx.fill();
            }
        
            // selection ring (bases will also highlight if selectable)
            if (u.id === selectedUnitId) {
              ctx.beginPath();
              ctx.arc(u.x, u.y, half + 4, 0, Math.PI * 2);
              ctx.strokeStyle = "red";
              ctx.lineWidth = 2;
              ctx.stroke();
            }
          }
        
          if (moveTarget) {
            ctx.beginPath();
            ctx.arc(moveTarget.x, moveTarget.y, 6, 0, Math.PI * 2);
            ctx.strokeStyle = "blue";
            ctx.lineWidth = 2;
            ctx.stroke();
          }
        }

    let lastTimestamp = null;
    function gameLoop(timestamp) {
      if (!lastTimestamp) lastTimestamp = timestamp;
      const dt = timestamp - lastTimestamp;
      lastTimestamp = timestamp;
      drawUnits();

      window.requestAnimationFrame(gameLoop);
    }

    // initialization
    fetchUnits();
    setInterval(fetchUnits, 100)
    window.requestAnimationFrame(gameLoop);
  </script>
</body>
</html>


"""
selected_unit_id = None  # server-side info about selection

units = [UAVUnits.LoiteringMunition("Termopile", 50, 55, UAVUnits.UnitState.Landed, (100,100), "static/images/uav.png", UAVUnits.ArmourType.Unarmored, 1,1.7,0.0083, 0.0138,1.0,UAVUnits.ExplosiveType.HEAT)]

aaUnits = [AntiAirUnits.AntiAir("Wuefkin",20,0, UAVUnits.UnitState.Idle, (400,400), "static/images/antiAir.png", UAVUnits.ArmourType.LightArmour, 2, 150, 3, 1, 2, AntiAirUnits.AAStatus.Idle)]

logBases = [LogHub.LogHub("14 Baza Logistyczna", (150,150), "static/images/base.png",1, 300)]

ground_retransmitters = []

pending_attacks = {}

@app.route("/")
def index():
    return render_template_string(PAGE_TMPL, width=MAP_WIDTH, height=MAP_HEIGHT)


# --- MAP IMAGE (background only) ---
@app.route("/map")
def map_image():
    img = Image.new("RGB", (MAP_WIDTH, MAP_HEIGHT), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # draw light grid
    step = 50
    for x in range(0, MAP_WIDTH, step):
        draw.line((x, 0, x, MAP_HEIGHT), fill=(230, 230, 230))
    for y in range(0, MAP_HEIGHT, step):
        draw.line((0, y, MAP_WIDTH, y), fill=(230, 230, 230))

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


# --- API: units ---

@app.route("/units")
def get_units():
    unit_data = []

    # include UAVs, AA and bases
    all_units = units + aaUnits + logBases + ground_retransmitters

    for u in all_units:
        # base dictionary common for everything
        data = {
            "id": getattr(u, "id", None),   # bases don't have id yet, we'll fix below
            "name": getattr(u, "name", "Unknown"),
            "x": u.positionX,
            "y": u.positionY,
            "image": getattr(u, "image", None),
            "player": getattr(u, "player", 0),
            "unit_class": u.__class__.__name__,
            "size": 28
        }

        # extra fields for UAVs
        if isinstance(u, UAVUnits.UAV):
            data.update({
                "state": u.state.name,
                "chanceToHit": getattr(u, "chanceToHit", None),
                "baseSpeed": getattr(u, "baseSpeed", None),
                "armourType": u.armourType.name if hasattr(u, "armourType") else None,
                "currentBattery": round(u.currentBattery, 2),
                "currentWeight": u.currentWeight,
                "idleBatteryDrainPerTick": u.idleBatteryDrainPerTick,
                "moveBatteryDrainPerTick": u.moveBatteryDrainPerTick,
            })

        # extra fields for LoiteringMunition
        if isinstance(u, UAVUnits.LoiteringMunition):
            data.update({
                "payload": u.payload,
                "explosiveType": u.explosiveType.name,
            })

        # extra fields for AntiAir
        if isinstance(u, AntiAirUnits.AntiAir):
            data.update({
                "state": u.state.name,
                "armourType": u.armourType.name if hasattr(u, "armourType") else None,
                "range": u.range,
                "aa_state": u.AAstate.name,
                "ammo": u.ammoCount
            })

        # extra fields for LogHub (the bases)
        if isinstance(u, LogHub.LogHub):
            # give bases a pseudo-id if they don't have one
            # simplest: index in list, but better to really give them an id once at creation
            data.update({
                "transmissionRange": u.transmissionRange,
                "available_retransmitters": getattr(u, "available_retransmitters",0)
            })

        if isinstance(u, LogHub.GroundRetransmitter):
            data.update({
                "transmissionRange": u.transmissionRange,
                "parent_base_id": u.parent_base_id
            })

        unit_data.append(data)

    return jsonify(unit_data)

# --- API: select unit ---
@app.route("/select_unit", methods=["POST"])
def select_unit():
    global selected_unit_id
    data = request.get_json()
    unit_id = data.get("id")
    selected_unit_id = unit_id
    # here you can run any game logic you want
    # e.g. mark unit, open unit detail, change its state, etc.
    print(f"[SERVER] Unit selected: {unit_id}")
    return jsonify({"status": "ok", "selected": unit_id})

@app.route("/move_unit", methods=["POST"])
def move_unit():
    data = request.get_json()
    unit_id = data.get("id")
    x = data.get("x")
    y = data.get("y")

    # find the unit by ID
    for u in units:
        if u.id == unit_id and u.player == PLAYER1:

            if isinstance(u, UAVUnits.UAV):
                if not is_uav_in_comm(u, logBases, ground_retransmitters):
                    return jsonify({"status": "error", "message": "UAV out of transmission range"}), 400

            u.move_unit((x, y))
            print(f"[SERVER] Moving unit {unit_id} to ({x}, {y})")
            return jsonify({"status": "ok", "unit_id": unit_id, "destination": (x, y)})

    return jsonify({"status": "error", "message": "unit not found"}), 404

@app.route("/attack_unit", methods=["POST"])
def attack_unit():
    data = request.get_json()
    attacker_id = data.get("attacker_id")
    target_id = data.get("target_id")

    # we won’t attack right now – we just store the intent
    global pending_attacks

    # optional: validate attacker exists and is LM
    attacker = next((u for u in units if u.id == attacker_id), None)
    if attacker is None:
        return jsonify({"status": "error", "message": "attacker not found"}), 404

    if not isinstance(attacker, UAVUnits.LoiteringMunition):
        return jsonify({"status": "error", "message": "attacker is not LoiteringMunition"}), 400

    # also check that target exists (in any list)
    all_units = units + aaUnits
    target = next((u for u in all_units if u.id == target_id), None)
    if target is None:
        return jsonify({"status": "error", "message": "target not found"}), 404

    # store order
    pending_attacks[attacker_id] = target_id

    return jsonify({"status": "ok", "message": "attack order stored"})

@app.route("/place_retransmitter", methods=["POST"])
def place_retransmitter():
    data = request.get_json()
    base_id = data.get("base_id")
    x = data.get("x")
    y = data.get("y")

    # find the base
    base = next((b for b in logBases if b.id == base_id), None)
    if base is None:
        return jsonify({"status": "error", "message": "base not found"}), 404

    # check if base still has quota
    if getattr(base, "available_retransmitters", 0) <= 0:
        return jsonify({"status": "error", "message": "this base has no retransmitters left"}), 400

    # check that (x, y) is inside base transmission range
    dx = x - base.positionX
    dy = y - base.positionY
    dist = math.hypot(dx, dy)
    if dist > base.transmissionRange:
        return jsonify({"status": "error", "message": "point outside base transmission range"}), 400

    # create retransmitter
    retrans = LogHub.GroundRetransmitter(
        name=f"RT-{base_id}",
        position=(x, y),
        image="static/images/retransmitter.png",
        player=base.player,
        transmissionRange=200,
        parent_base_id=base_id
    )
    ground_retransmitters.append(retrans)

    # decrease available on the base
    base.available_retransmitters -= 1

    return jsonify({"status": "ok", "available": base.available_retransmitters})



def is_uav_in_comm(uav, bases, retransmitters):
    # uav.player must match base.player
    for b in bases:
        if b.player == uav.player:
            dx = uav.positionX - b.positionX
            dy = uav.positionY - b.positionY
            dist = math.hypot(dx, dy)
            if dist <= b.transmissionRange:
                return True

    for r in retransmitters:
        if r.player == uav.player:
            dx = uav.positionX - r.positionX
            dy = uav.positionY - r.positionY
            dist = math.hypot(dx, dy)
            if dist <= r.transmissionRange:
                return True
    return False

def game_loop():
    dt = 1.0/TICK_RATE
    global units, aaUnits
    while True:
        for u in units:
            if isinstance(u, UAVUnits.UAV):
                if not is_uav_in_comm(u, logBases, ground_retransmitters):
                    u.destination = None
                    u.state = UAVUnits.UnitState.Idle
                    u.tick_unit(dt)
                    continue
            u.tick_unit(dt)

        for aa in aaUnits:
            aa.tickAA(dt, units)
        time.sleep(dt)

        before_uav = len(units)
        before_aa = len(aaUnits)

        for attacker_id in list(pending_attacks.keys()):
            target_id = pending_attacks[attacker_id]

            # find attacker + target again (they may have moved or died)
            attacker = next((u for u in units if u.id == attacker_id), None)
            all_units = units + aaUnits
            target = next((u for u in all_units if u.id == target_id), None)

            # if attacker or target is gone/destroyed -> drop order
            if attacker is None or attacker.state == UAVUnits.UnitState.Destroyed \
               or target is None or target.state == UAVUnits.UnitState.Destroyed:
                pending_attacks.pop(attacker_id, None)
                continue

            # compute distance
            dx = target.positionX - attacker.positionX
            dy = target.positionY - attacker.positionY
            dist = math.hypot(dx, dy)

            if dist <= ATTACK_RANGE:
                # in range -> perform attack
                attacker.attack(target)
                # remove order (LM will likely destroy itself too)
                pending_attacks.pop(attacker_id, None)
            else:
                # not in range -> keep chasing
                # we order the LM to move toward the *current* target position
                attacker.move_unit((target.positionX, target.positionY))

        units = [u for u in units if u.state != UAVUnits.UnitState.Destroyed]
        aaUnits = [aa for aa in aaUnits if aa.state != UAVUnits.UnitState.Destroyed]

        if len(units) != before_uav or len(aaUnits) != before_aa:
            print(f"[SERVER] Destroyed units removed: "
                  f"{before_uav - len(units)} UAVs, {before_aa - len(aaUnits)} AA units.")


threading.Thread(target=game_loop, daemon=True).start()

if __name__ == "__main__":
    # run: python app.py
    app.run(debug=False)
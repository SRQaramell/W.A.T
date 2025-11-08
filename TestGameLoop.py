import threading
import time
import math

from flask import Flask, request, send_file, render_template_string, jsonify
from io import BytesIO
from PIL import Image, ImageDraw
import UAVUnits, AntiAirUnits
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

    let units = [];             // will be fetched from server
    let selectedUnitId = null;
    let moveTarget = null;      // { x:…, y:… } or null

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
    
          // 👇 NEW: if we have something selected, show its latest data
          if (selectedUnitId !== null) {
            const selected = units.find(u => u.id === selectedUnitId);
            if (selected) {
              updateInfoPanel(selected);
            } else {
              // selected unit disappeared
              infoPanel.innerHTML = "No unit selected.";
              selectedUnitId = null;
            }
          }
        })
        .catch(err => console.error("Failed to fetch units:", err));
    }

        canvas.addEventListener("click", (event) => {
          const rect = canvas.getBoundingClientRect();
          const scaleX = canvas.width / rect.width;
          const scaleY = canvas.height / rect.height;
        
          const clickX = (event.clientX - rect.left) * scaleX;
          const clickY = (event.clientY - rect.top)  * scaleY;
        
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
      let html = "<ul>";
      for (const key in u) {
        if (u.hasOwnProperty(key) && key !== "_img") {
          html += `<li><strong>${key}:</strong> ${u[key]}</li>`;
        }
      }
      html += "</ul>";
      infoPanel.innerHTML = html;
    }

        function drawUnits() {
          ctx.clearRect(0, 0, canvas.width, canvas.height);
        
          for (const u of units) {
            const size = u.size || 24;
            const half = size / 2;
        
            // If this is AntiAir, draw its range first (so circle is under the icon)
            if (u.unit_class === "AntiAir" && u.range) {
              ctx.beginPath();
              ctx.arc(u.x, u.y, u.range, 0, Math.PI * 2);
              ctx.strokeStyle = "rgba(0, 128, 255, 0.6)";
              ctx.lineWidth = 2;
              ctx.stroke();
        
              // optional fill to visualize area
              ctx.fillStyle = "rgba(0, 128, 255, 0.08)";
              ctx.fill();
            }
        
            const img = u._img;
            if (img && img.complete) {
              // Draw base image
              ctx.drawImage(img, u.x - half, u.y - half, size, size);
            
              // Overlay color tint based on player
              ctx.save();
              ctx.globalAlpha = 0.35;
              if (u.player === 1) ctx.fillStyle = "blue";
              else if (u.player === 2) ctx.fillStyle = "red";
              else ctx.fillStyle = "gray";
              ctx.beginPath();
              ctx.rect(u.x - half, u.y - half, size, size);
              ctx.fill();
              ctx.restore();
            } else {
              // Fallback: colored circle if no image
              ctx.beginPath();
              ctx.arc(u.x, u.y, half, 0, Math.PI * 2);
              if (u.player === 1) ctx.fillStyle = "blue";
              else if (u.player === 2) ctx.fillStyle = "red";
              else ctx.fillStyle = "gray";
              ctx.fill();
            }
        
            // selection ring
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

    # include both UAVs and AA
    all_units = units + aaUnits

    for u in all_units:
        data = {
            "id": u.id,
            "name": u.name,
            "x": u.positionX,
            "y": u.positionY,
            "image": u.image,
            "state": u.state.name,
            "player": u.player,
            "unit_class": u.__class__.__name__,
            "chanceToHit": getattr(u, "chanceToHit", None),
            "baseSpeed": getattr(u, "baseSpeed", None),
            "armourType": u.armourType.name if hasattr(u, "armourType") else None,
            "size": 28  # small convenience so we can draw a square/circle
        }

        # extra fields for all UAVs
        if isinstance(u, UAVUnits.UAV):
            data.update({
                "currentBattery": round(u.currentBattery, 2),
                "currentWeight": u.currentWeight,
                "idleBatteryDrainPerTick": u.idleBatteryDrainPerTick,
                "moveBatteryDrainPerTick": u.moveBatteryDrainPerTick,
            })

        # extra fields for loitering munition
        if isinstance(u, UAVUnits.LoiteringMunition):
            data.update({
                "payload": u.payload,
                "explosiveType": u.explosiveType.name,
            })

        # extra fields for AntiAir
        if isinstance(u, AntiAirUnits.AntiAir):
            data.update({
                "range": u.range,
                "aa_state": u.AAstate.name,
                "ammo": u.ammoCount
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



def game_loop():
    dt = 1.0/TICK_RATE
    global units, aaUnits
    while True:
        for u in units:
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
    app.run(debug=True)
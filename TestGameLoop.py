import threading
import time
import math

from flask import Flask, request, send_file, render_template_string, jsonify
from io import BytesIO
from PIL import Image, ImageDraw
import UAVUnits, AntiAirUnits, LogHub

app = Flask(__name__)

MAP_WIDTH = 1024
MAP_HEIGHT = 1024
TICK_RATE = 10
PLAYER1 = 1
ATTACK_RANGE = 3

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
    /* NEW: overlay controls */
    #overlayMenu {
      position: fixed;
      top: 10px;
      left: 10px;
      background: rgba(255,255,255,0.9);
      border: 1px solid #ccc;
      border-radius: 4px;
      padding: 8px 10px;
      font-family: sans-serif;
      font-size: 13px;
      z-index: 999;
    }
    #overlayMenu label {
      display: block;
      margin-bottom: 4px;
      cursor: pointer;
    }
  </style>
</head>
<body>
    <div id="overlayMenu">
      <label>
        <input type="checkbox" id="chkTransmission" checked>
        Show transmission zones
      </label>
      <label>
        <input type="checkbox" id="chkEnemyAA" checked>
        Show enemy AA ranges
      </label>
      <hr>
      <div><strong>Admin spawn</strong></div>
      <div>
        <label>Type:
          <select id="adminUnitType">
            <option value="LoiteringMunition">LoiteringMunition</option>
            <option value="AntiAir">AntiAir</option>
            <option value="LogHub">LogHub</option>
            <option value="GroundRetransmitter">GroundRetransmitter</option>
          </select>
        </label>
      </div>
      <div>
        <label>Player:
          <select id="adminPlayer">
            <option value="1">Player 1</option>
            <option value="2">Player 2</option>
            <option value="3">Player 3</option>
          </select>
        </label>
      </div>
      <div>
        <label>
          <input type="checkbox" id="adminPlaceMode">
          Click map to place
        </label>
      </div>
      <p id="adminMsg" style="font-size:11px;color:#333;"></p>
    </div>


  <canvas id="canvas" width="1024" height="1024"></canvas>
  <div id="infoPanel">
    <h2>Selected Unit Info</h2>
    <div id="unitInfo">No unit selected.</div>
  </div>

  <script>
    const canvas = document.getElementById("canvas");
    const ctx = canvas.getContext("2d");
    const infoPanel = document.getElementById("unitInfo");
    const mapImage = new Image();
    mapImage.src = "static/images/sampleMap.png";
    let mapLoaded = false;
    mapImage.onload = () => {
      mapLoaded = true;
    };

    // NEW: visibility flags
    let showTransmission = true;
    let showEnemyAA = true;

    // assume local player is 1 (server also uses PLAYER1 = 1)
    const localPlayer = 1;

    const chkTransmission = document.getElementById("chkTransmission");
    const chkEnemyAA = document.getElementById("chkEnemyAA");
    
    const adminUnitType = document.getElementById("adminUnitType");
    const adminPlayer = document.getElementById("adminPlayer");
    const adminPlaceModeChk = document.getElementById("adminPlaceMode");
    const adminMsg = document.getElementById("adminMsg");
    
    adminPlaceModeChk.addEventListener("change", () => {
      adminPlaceMode = adminPlaceModeChk.checked;
      if (adminPlaceMode) {
        adminMsg.textContent = "Admin mode ON: click on the map to place unit.";
      } else {
        adminMsg.textContent = "";
      }
    });

    chkTransmission.addEventListener("change", () => {
      showTransmission = chkTransmission.checked;
    });
    chkEnemyAA.addEventListener("change", () => {
      showEnemyAA = chkEnemyAA.checked;
    });

    let placeRetransmitterMode = false;
    let placingBaseId = null;
    let placingBaseData = null;
    
    let spawnUavMode = false;
    let spawnUavBaseId = null;
    let spawnUavBaseData = null;

    let adminPlaceMode = false;
    let adminUnitTypeSel = null;
    let adminPlayerSel = null;

    let placeRtFromKeyboard = false;
    let spawnUavFromKeyboard = false;

    let units = [];             // will be fetched from server
    let selectedUnitId = null;
    let selectedUnitSnapshot = null;
    let moveTarget = null;      // { x:…, y:… } or null

    function startRetransmitterPlacing(baseId, baseData) {
      placeRetransmitterMode = true;
      placingBaseId = baseId;
      placingBaseData = baseData;
    }

    function getSelectedUnit() {
      if (selectedUnitId === null) return null;
      return units.find(u => u.id === selectedUnitId) || null;
    }

    function startUavSpawn(baseId, baseData) {
      spawnUavMode = true;
      spawnUavBaseId = baseId;
      spawnUavBaseData = baseData;
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
      if (u.unit_class === "LogHub") {
        snap.available_retransmitters = u.available_retransmitters;
      }
      if (u.unit_class === "UAV" || u.unit_class === "LoiteringMunition") {
        snap.currentBattery = u.currentBattery;
        snap.state = u.state;
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
      if (a.unit_class === "LogHub") {
        same = same && a.available_retransmitters === b.available_retransmitters;
      }
        if (a.unit_class === "UAV" || a.unit_class === "LoiteringMunition") {
          same = same &&
            a.currentBattery === b.currentBattery &&
            a.state === b.state;
        }
      return same;
    }

    function fetchUnits() {
      fetch("/units")
        .then(res => res.json())
        .then(data => {
          units = data;
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
                selectedUnitSnapshot = makeUnitSnapshot(selected);
              }
            } else {
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
    // ADMIN PLACE?
        if (adminPlaceMode) {
          const rect = canvas.getBoundingClientRect();
          const scaleX = canvas.width / rect.width;
          const scaleY = canvas.height / rect.height;
          const clickX = (event.clientX - rect.left) * scaleX;
          const clickY = (event.clientY - rect.top)  * scaleY;
        
          fetch("/admin_spawn", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              unit_type: adminUnitType.value,
              player: adminPlayer.value,
              x: clickX,
              y: clickY
            })
          })
          .then(res => res.json())
          .then(d => {
            if (d.status === "ok") {
              adminMsg.textContent = "Spawned " + d.spawned + " for player " + adminPlayer.value;
              // refresh units so we see it immediately
              fetchUnits();
            } else {
              adminMsg.textContent = d.message || "Error spawning";
            }
          })
          .catch(err => {
            console.error(err);
            adminMsg.textContent = "Error spawning";
          });
        
          // don't let the normal click logic run
          return;
        }

    
      const rect = canvas.getBoundingClientRect();
      const scaleX = canvas.width / rect.width;
      const scaleY = canvas.height / rect.height;

      const clickX = (event.clientX - rect.left) * scaleX;
      const clickY = (event.clientY - rect.top)  * scaleY;

      // 0. placing retransmitter?
      if (placeRetransmitterMode && placingBaseId !== null) {
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
                    selectedUnitSnapshot = makeUnitSnapshot(baseNow);
                }
            });
            const chk = document.getElementById("placeRtChk");
            const hint = document.getElementById("placeHint");
            if (chk) chk.checked = false;
            if (hint) hint.textContent = "";
          } else {
            alert(d.message || "Error placing retransmitter");
          }
        })
        .catch(err => console.error(err));

        return;
      }

      // 0b. spawning UAV from base?
      if (spawnUavMode && spawnUavBaseId !== null) {
        fetch("/spawn_uav", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            base_id: spawnUavBaseId,
            x: clickX,
            y: clickY
          })
        })
        .then(res => res.json())
        .then(d => {
          if (d.status === "ok") {
            // stop spawn mode
            spawnUavMode = false;
            const baseId = spawnUavBaseId;
            spawnUavBaseId = null;
            spawnUavBaseData = null;
    
            // refresh units and panel so we see updated current_spawned_uavs
            fetchUnits().then(() => {
              const baseNow = units.find(u => u.id === baseId);
              if (baseNow) {
                updateInfoPanel(baseNow);
                selectedUnitSnapshot = makeUnitSnapshot(baseNow);
              }
            });
          } else {
            alert(d.message || "Error spawning UAV");
          }
        })
        .catch(err => console.error(err));
    
        return;
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

      const selected = selectedUnitId !== null
          ? units.find(u => u.id === selectedUnitId)
          : null;

      // 2. Ctrl+click -> attack (LM vs enemy)
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
          fetchUnits();
        })
        .catch(err => console.error(err));

        return;
      }

      // 3. select unit
      if (clickedUnit) {
        selectedUnitId = clickedUnit.id;
        moveTarget = null;
        updateInfoPanel(clickedUnit);
        return;
      }

      // 4. move
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
    
    document.addEventListener("keydown", (e) => {
      // avoid repeating when key is held down and browser fires repeat events
      if (e.repeat) return;
    
      const selected = getSelectedUnit();
      // we only want to start these modes if a LogHub (base) is selected
      const isBaseSelected = selected && selected.unit_class === "LogHub";
    
      // R -> place retransmitter
      if (e.key === "r" || e.key === "R") {
        if (isBaseSelected) {
          // check if base still has retransmitters
          const avail = selected.available_retransmitters ?? 0;
          if (avail > 0) {
            startRetransmitterPlacing(selected.id, selected);
            placeRtFromKeyboard = true;
            // optional: show hint in panel
            const hint = document.getElementById("placeHint");
            if (hint) {
              hint.textContent = "Click on the map inside the base range to place retransmitter…";
            } else {
              // you can also append to infoPanel if you want
            }
          } else {
            // optional: alert("No retransmitters left");
          }
        }
      }
    
      // L -> spawn loitering munition
      if (e.key === "l" || e.key === "L") {
        if (isBaseSelected) {
          const curr = selected.current_spawned_uavs ?? 0;
          const max = selected.max_spawned_uavs ?? 5;
          if (curr < max) {
            startUavSpawn(selected.id, selected);
            spawnUavFromKeyboard = true;
            // optional UI hint
            const existingMsg = document.getElementById("spawnUavMsg");
            if (!existingMsg) {
              const panel = document.getElementById("unitInfo");
              if (panel) {
                panel.innerHTML += `<p id="spawnUavMsg">Click on the map to set UAV target…</p>`;
              }
            }
          } else {
            // optional: alert("No UAVs left");
          }
        }
      }
    });
    
    document.addEventListener("keyup", (e) => {
      // if user releases R and we were in RT mode because of keyboard, exit
      if ((e.key === "r" || e.key === "R") && placeRtFromKeyboard) {
        placeRetransmitterMode = false;
        placingBaseId = null;
        placingBaseData = null;
        placeRtFromKeyboard = false;
        const chk = document.getElementById("placeRtChk");
        const hint = document.getElementById("placeHint");
        if (chk) chk.checked = false;
        if (hint) hint.textContent = "";
      }
    
      // if user releases L and we were in spawn mode because of keyboard, exit
      if ((e.key === "l" || e.key === "L") && spawnUavFromKeyboard) {
        spawnUavMode = false;
        spawnUavBaseId = null;
        spawnUavBaseData = null;
        spawnUavFromKeyboard = false;
        const msg = document.getElementById("spawnUavMsg");
        if (msg) msg.textContent = "";
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
          const curr = u.current_spawned_uavs ?? 0;
          const max = u.max_spawned_uavs ?? 5;
        
          html += `<p><strong>UAVs:</strong> ${curr} / ${max}</p>`;
          html += `<button id="placeRtBtn">Place retransmitter</button>`;
          html += `<button id="spawnUavBtn" ${curr >= max ? "disabled" : ""}>Spawn loitering munition</button>`;
        
          if (wasPlacingThisBase) {
            html += `<p id="placeMsg">Click on the map inside the base range to place retransmitter…</p>`;
          }
        }

      infoPanel.innerHTML = html;

        if (isBase) {
          const btn = document.getElementById("placeRtBtn");
          if (btn) {
            btn.addEventListener("click", () => {
              startRetransmitterPlacing(u.id, u);
              const p = document.getElementById("placeMsg");
              if (p) {
                p.textContent = "Click on the map inside the base range to place retransmitter…";
              } else {
                infoPanel.innerHTML += `<p id="placeMsg">Click on the map inside the base range to place retransmitter…</p>`;
              }
            });
          }
        
          const uavBtn = document.getElementById("spawnUavBtn");
          if (uavBtn && !(u.current_spawned_uavs >= u.max_spawned_uavs)) {
            uavBtn.addEventListener("click", () => {
              startUavSpawn(u.id, u);
              // optional: show small hint
              infoPanel.innerHTML += `<p id="spawnUavMsg">Click on the map to set UAV target…</p>`;
            });
          }
        }
    }

    function drawUnits() {
        if (mapLoaded) {
          ctx.drawImage(mapImage, 0, 0, canvas.width, canvas.height);
        } else {
          ctx.fillStyle = "#303030"; // fallback background
          ctx.fillRect(0, 0, canvas.width, canvas.height);
        }

      for (const u of units) {
        const size = u.size || 24;
        const half = size / 2;

        // 1) draw range for enemy AntiAir (NEW condition)
        if (
          u.unit_class === "AntiAir" &&
          u.range &&
          showEnemyAA &&
          u.player !== localPlayer
        ) {
          ctx.beginPath();
          ctx.arc(u.x, u.y, u.range, 0, Math.PI * 2);
          ctx.strokeStyle = "rgba(0, 128, 255, 0.6)";
          ctx.lineWidth = 2;
          ctx.stroke();
          ctx.fillStyle = "rgba(0, 128, 255, 0.08)";
          ctx.fill();
        }

        // 2) draw transmission range for bases and ground retransmitters (toggable)
        if (showTransmission && u.transmissionRange) {
          if (
          (u.unit_class === "LogHub" || u.unit_class === "GroundRetransmitter") && 
          u.player === 1
          ) {
            ctx.beginPath();
            ctx.arc(u.x, u.y, u.transmissionRange, 0, Math.PI * 2);
            ctx.strokeStyle = "rgba(0, 200, 0, 0.6)";
            ctx.lineWidth = 2;
            ctx.stroke();
            ctx.fillStyle = "rgba(0, 200, 0, 0.05)";
            ctx.fill();
          }
        }

        // draw unit/base icon
        const img = u._img;
        if (img && img.complete) {
          ctx.drawImage(img, u.x - half, u.y - half, size, size);
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
                "available_retransmitters": getattr(u, "available_retransmitters",0),
                "current_spawned_uavs": getattr(u, "current_spawned_uavs", 0),
                "max_spawned_uavs": getattr(u, "max_spawned_uavs", 5)
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

@app.route("/spawn_uav", methods=["POST"])
def spawn_uav():
    data = request.get_json()
    base_id = data.get("base_id")
    target_x = data.get("x")
    target_y = data.get("y")

    # find the base
    base = next((b for b in logBases if b.id == base_id), None)
    if base is None:
        return jsonify({"status": "error", "message": "base not found"}), 404

    # quota check
    max_uavs = getattr(base, "max_spawned_uavs", 5)
    current_uavs = getattr(base, "current_spawned_uavs", 0)
    if current_uavs >= max_uavs:
        return jsonify({"status": "error", "message": "this base has no UAVs left"}), 400

    # create Loitering Munition at base position
    lm = UAVUnits.LoiteringMunition(
        name=f"LM-{base.id}-{current_uavs+1}",
        chanceToHit=50,
        baseSpeed=55,
        state=UAVUnits.UnitState.Idle,
        position=(base.positionX, base.positionY),
        image="static/images/uav.png",
        armourType=UAVUnits.ArmourType.Unarmored,
        player=base.player,
        currentWeight=1.7,
        idleBatteryDrainPerTick=0.0083,
        moveBatteryDrainPerTick=0.0138,
        payload=1.0,
        explosiveType=UAVUnits.ExplosiveType.HEAT
    )

    # remember which base spawned it, so we can give the slot back when it dies
    lm.parent_base_id = base.id

    # set its destination to user click
    lm.move_unit((target_x, target_y))

    # add to live units list
    units.append(lm)

    # consume base slot
    base.current_spawned_uavs = current_uavs + 1

    return jsonify({"status": "ok", "uav_id": lm.id})

@app.route("/admin_spawn", methods=["POST"])
def admin_spawn():
    data = request.get_json()
    unit_type = data.get("unit_type")      # e.g. "LoiteringMunition", "AntiAir", "LogHub", "GroundRetransmitter"
    player = int(data.get("player", 1))
    x = float(data.get("x"))
    y = float(data.get("y"))

    global units, aaUnits, logBases, ground_retransmitters

    if unit_type == "LoiteringMunition":
        lm = UAVUnits.LoiteringMunition(
            name=f"LM-admin-{len(units)}",
            chanceToHit=50,
            baseSpeed=55,
            state=UAVUnits.UnitState.Landed,
            position=(x, y),
            image="static/images/uav.png",
            armourType=UAVUnits.ArmourType.Unarmored,
            player=player,
            currentWeight=1.7,
            idleBatteryDrainPerTick=0.0083,
            moveBatteryDrainPerTick=0.0138,
            payload=1.0,
            explosiveType=UAVUnits.ExplosiveType.HEAT
        )
        units.append(lm)
        return jsonify({"status": "ok", "spawned": "LoiteringMunition", "id": lm.id})

    elif unit_type == "AntiAir":
        aa = AntiAirUnits.AntiAir(
            name=f"AA-admin-{len(aaUnits)}",
            chanceToHit=35,
            baseSpeed=0,
            state=UAVUnits.UnitState.Idle,
            position=(x, y),
            image="static/images/antiAir.png",
            armourType=UAVUnits.ArmourType.LightArmour,
            player=player,
            range=150,
            ammoCount=5,
            aimTime=1.0,
            timeBetweenShots=2.0,
            AAstate=AntiAirUnits.AAStatus.Idle
        )
        aaUnits.append(aa)
        return jsonify({"status": "ok", "spawned": "AntiAir"})

    elif unit_type == "LogHub":
        base = LogHub.LogHub(
            name=f"Base-admin-{len(logBases)}",
            position=(x, y),
            image="static/images/base.png",
            player=player,
            transmissionRange=300
        )
        logBases.append(base)
        return jsonify({"status": "ok", "spawned": "LogHub", "id": base.id})

    elif unit_type == "GroundRetransmitter":
        rt = LogHub.GroundRetransmitter(
            name=f"RT-admin-{len(ground_retransmitters)}",
            position=(x, y),
            image="static/images/retransmitter.png",
            player=player,
            transmissionRange=200,
            parent_base_id=-1
        )
        ground_retransmitters.append(rt)
        return jsonify({"status": "ok", "spawned": "GroundRetransmitter"})

    else:
        return jsonify({"status": "error", "message": "unknown unit type"}), 400


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
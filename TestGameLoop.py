import threading
import time
import math

from flask import Flask, request, send_file, render_template_string, jsonify
from io import BytesIO
from PIL import Image, ImageDraw
import UAVUnits, AntiAirUnits, LogHub, GroundUnits

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
      /* we can keep overflow hidden here because the scroll will be on #mapContainer */
      overflow: hidden;
    }
    
    /* NEW: scrollable map area */
    #mapContainer {
      flex: 1 1 auto;
      overflow: auto;             /* enables scrollbars */
      background: #f0f0f0;
      display: flex;
      justify-content: flex-end;  /* anchors the canvas to the right edge */
      align-items: flex-start;
    }
    
    /* canvas can stay block */
    #canvas {
      display: block;
    }
    
    /* info panel stays the same */
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
            <option value="RetransmiterUAV">RetransmiterUAV</option>
            <option value="ElectronicWarfare">ElectronicWarfare</option>
          </select>
        </label>
      </div>
        <div style="margin-top:6px;">
          <label>Jamming range (px):
            <input id="adminJammingRange" type="number" value="200" style="width:80px;">
          </label>
        </div>
        <div style="margin-top:4px;">
          <label>Jamming freqs (comma): 
            <input id="adminJammingFreq" type="text" value="2400,5800" style="width:120px;">
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
        <div>
          <label>
            <input type="checkbox" id="adminDestroyMode">
            Click unit/structure to DESTROY
          </label>
        </div>
      <hr>
      <div><strong>Admin supply</strong></div>
      <div>
        <label>Supply:
          <select id="adminSupplyType">
            <option value="AAMunition">AA munition</option>
            <option value="Fuel">Fuel</option>
            <option value="Food">Food</option>
            <option value="Munition">Munition</option>
            <option value="Explosives">Explosives</option>
            <option value="MedicalSupplies">Medical supplies</option>
            <option value="Gruz200">Gruz200</option>
            <option value="Gruz300">Gruz300</option>
            <option value="SpareParts">Spare parts</option>
            <option value="Other">Other</option>
          </select>
        </label>
      </div>
      <div>
        <label>Amount:
          <input id="adminSupplyAmount" type="number" value="10" style="width:70px;">
        </label>
      </div>
      <button id="adminAddSupplyBtn" style="margin-top:4px;">Add to selected LogHub</button>

      <p id="adminMsg" style="font-size:11px;color:#333;"></p>
    </div>


    <div id="mapContainer">
      <canvas id="canvas" width="1024" height="1024"></canvas>
    </div>
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
    const adminDestroyModeChk = document.getElementById("adminDestroyMode");
    const adminSupplyType = document.getElementById("adminSupplyType");
    const adminSupplyAmount = document.getElementById("adminSupplyAmount");
    const adminAddSupplyBtn = document.getElementById("adminAddSupplyBtn");
    
    let adminDestroyMode = false;
    
    adminAddSupplyBtn.addEventListener("click", () => {
      if (selectedUnitId === null) {
        adminMsg.textContent = "Select a LogHub first.";
        return;
      }
      const selected = units.find(u => u.id === selectedUnitId);
      if (!selected || selected.unit_class !== "LogHub") {
        adminMsg.textContent = "Selected object is not a LogHub.";
        return;
      }

      const supply = adminSupplyType.value;
      const amount = parseInt(adminSupplyAmount.value, 10) || 0;

      fetch("/admin_add_supply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          base_id: selectedUnitId,
          supply_type: supply,
          amount: amount
        })
      })
      .then(r => r.json())
      .then(d => {
        if (d.status === "ok") {
          adminMsg.textContent = "Supply added.";
          // refresh units so info panel updates
        const u = units.find(x => x.id === selectedUnitId);
        if (u && d.storage) {
          u.storage = d.storage;
          updateInfoPanel(u); // instant refresh
        }
          fetchUnits();
        } else {
          adminMsg.textContent = d.message || "Error adding supply";
        }
      })
      .catch(err => {
        console.error(err);
        adminMsg.textContent = "Error adding supply";
      });
    });

    
    adminDestroyModeChk.addEventListener("change", () => {
      adminDestroyMode = adminDestroyModeChk.checked;
      if (adminDestroyMode) {
        adminMsg.textContent = "Destroy mode ON: click any unit/structure to remove it.";
        // optional: turn off place mode, so they don’t clash
        adminPlaceModeChk.checked = false;
        adminPlaceMode = false;
      } else {
        adminMsg.textContent = "";
      }
    });
    
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
    
    let simPaused = false;
    
    let spawnUavMode = false;
    let spawnUavBaseId = null;
    let spawnUavBaseData = null;

    let spawnRtUavMode = false;
    let spawnRtUavBaseId = null;
    let spawnRtUavBaseData = null;

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

    function startRtUavSpawn(baseId, baseData) {
      spawnRtUavMode = true;
      spawnRtUavBaseId = baseId;
      spawnRtUavBaseData = baseData;
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
    
      // bases: we care about counters
      if (u.unit_class === "LogHub") {
        snap.available_retransmitters = u.available_retransmitters;
        snap.current_spawned_uavs = u.current_spawned_uavs;
        snap.max_spawned_uavs = u.max_spawned_uavs;
        snap.current_air_retransmitters = u.current_air_retransmitters;
        snap.max_air_retransmitters = u.max_air_retransmitters;
        snap.storage_json = JSON.stringify(u.storage || {});
      }
    
      // IMPORTANT: do NOT put battery/state/is_retransmitting here
      // for UAVs/retrans UAVs, because that changes every tick and will
      // force a full panel rebuild.
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
        same =
          same &&
          a.available_retransmitters === b.available_retransmitters &&
          a.current_spawned_uavs === b.current_spawned_uavs &&
          a.max_spawned_uavs === b.max_spawned_uavs &&
          a.current_air_retransmitters === b.current_air_retransmitters &&
          a.max_air_retransmitters === b.max_air_retransmitters;
          a.storage_json === JSON.stringify(b.storage || {});
      }
    
      // NOTE: we purposely do NOT compare battery/state for UAVs here
    
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
                // always refresh fast-changing stuff for retrans UAV
                if (selected.unit_class === "RetransmiterUAV") {
                  updateInfoPanelDynamic(selected);
                }
            
                // rebuild whole panel only if structure actually changed
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

      const rect = canvas.getBoundingClientRect();
      const scaleX = canvas.width / rect.width;
      const scaleY = canvas.height / rect.height;
      const clickX = (event.clientX - rect.left) * scaleX;
      const clickY = (event.clientY - rect.top)  * scaleY;
    
          // 1) ADMIN DESTROY?
          if (adminDestroyMode) {
            // find what we clicked, same as your selection logic later
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
        
            if (clickedUnit) {
              fetch("/admin_destroy", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ id: clickedUnit.id })
              })
              .then(res => res.json())
              .then(d => {
                if (d.status === "ok") {
                  adminMsg.textContent = "Destroyed " + d.destroyed_class + " (id=" + d.id + ")";
                  fetchUnits();
                } else {
                  adminMsg.textContent = d.message || "Error destroying";
                }
              })
              .catch(err => {
                console.error(err);
                adminMsg.textContent = "Error destroying";
              });
            } else {
              adminMsg.textContent = "No unit/structure under click.";
            }
        
            return; // stop normal click handling
          }

    // ADMIN PLACE?
        if (adminPlaceMode) {
          
            const payload = {
              unit_type: adminUnitType.value,
              player: adminPlayer.value,
              x: clickX,
              y: clickY
            };
            
            if (adminUnitType.value === "ElectronicWarfare") {
              const jamRange = parseInt(document.getElementById("adminJammingRange").value, 10) || 200;
              const jamFreqText = document.getElementById("adminJammingFreq").value || "";
              const jamFreqs = jamFreqText.split(",").map(s => parseFloat(s.trim())).filter(n => !Number.isNaN(n));
              payload.jammingRange = jamRange;
              payload.jammingFreq = jamFreqs;
            }
            
            fetch("/admin_spawn", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(payload)   // <-- send payload, not a new object
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
      
        if (spawnRtUavMode && spawnRtUavBaseId !== null) {
          fetch("/spawn_retrans_uav", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              base_id: spawnRtUavBaseId,
              x: clickX,
              y: clickY
            })
          })
          .then(res => res.json())
          .then(d => {
            if (d.status !== "ok") {
              alert(d.message || "Error spawning retrans UAV");
            }
            fetchUnits();
          })
          .catch(console.error);
        
          spawnRtUavMode = false;
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

        // 4. move (with queue when Shift is held)
        if (selectedUnitId !== null) {
          const isQueued = event.shiftKey === true;
        
          fetch("/move_unit", {
            method: "POST",
            headers:  { "Content-Type": "application/json" },
            body: JSON.stringify({
              id: selectedUnitId,
              x: clickX,
              y: clickY,
              queue: isQueued   // <--- tell server this should be added to queue
            })
          })
          .then(res => res.json())
          .then(data => {
            // refresh units so we see destination line etc.
            fetchUnits();
          })
          .catch(err => console.error(err));
        
          // optional: show last clicked point as target
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
      
        if (e.code === "Space") {
          e.preventDefault(); // so page doesn't scroll
          fetch("/toggle_pause", { method: "POST" })
            .then(r => r.json())
            .then(d => {
              if (d.status === "ok") {
                simPaused = d.paused;
                updatePauseBanner();
              }
            })
            .catch(console.error);
          return;
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
        if (!u.hasOwnProperty(key) || key === "_img" || key === "storage") continue;
        html += `<li><strong>${key}:</strong> ${u[key]}</li>`;
      }
      html += "</ul>";

      if (isBase) {
        const storage = u.storage || {};
        html += `<h3>Storage</h3>`;
        if (Object.keys(storage).length === 0) {
          html += `<p>(empty)</p>`;
        } else {
          html += `<ul>`;
          for (const [sName, sAmt] of Object.entries(storage)) {
            html += `<li>${sName}: ${sAmt}</li>`;
          }
          html += `</ul>`;
        }
      }

        if (isBase) {
          const curr = u.current_spawned_uavs ?? 0;
          const max = u.max_spawned_uavs ?? 5;
        
          html += `<p><strong>UAVs:</strong> ${curr} / ${max}</p>`;
          html += `<button id="placeRtBtn">Place retransmitter</button>`;
          html += `<button id="spawnUavBtn" ${curr >= max ? "disabled" : ""}>Spawn loitering munition</button>`;
        
          html += `<hr>`;
          html += `<p>Air retransmitters: ${u.current_air_retransmitters}/${u.max_air_retransmitters}</p>`;
          html += `<button id="spawnRtUavBtn" ${u.current_air_retransmitters >= u.max_air_retransmitters ? "disabled" : ""}>Spawn retrans UAV</button>`;
        
          if (wasPlacingThisBase) {
            html += `<p id="placeMsg">Click on the map inside the base range to place retransmitter…</p>`;
          }
        }

        const isRtUav = u.unit_class === "RetransmiterUAV";
        if (isRtUav) {
          // dynamic placeholder
          html += `<div id="unitInfoDynamic">
            <p>Battery: ${u.currentBattery ?? "?"}%</p>
            <p>State: ${u.state ?? "?"}</p>
            <p>Retransmitting: ${u.is_retransmitting ? "yes" : "no"}</p>
          </div>`;
        
          html += `
            <button id="toggleRtUavBtn">
              ${u.is_retransmitting ? "Disable retransmission" : "Enable retransmission"}
            </button>
            <p>Range: ${u.transmissionRange ?? "?"}</p>
          `;
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
        
          const rtUavBtn = document.getElementById("spawnRtUavBtn");
          if (rtUavBtn && u.current_air_retransmitters < u.max_air_retransmitters) {
            rtUavBtn.addEventListener("click", () => {
              // put UI into "next map click will spawn air retrans UAV for this base" mode
              startRtUavSpawn(u.id, u);
              // optional hint
              infoPanel.innerHTML += `<p id="spawnRtUavMsg">Click on the map to place retrans UAV…</p>`;
            });
          }
        
        if (u.unit_class === "ElectronicWarfare") {
          html += `<p><strong>Jamming range:</strong> ${u.jammingRange}</p>`;
          html += `<p><strong>Jamming freqs:</strong> ${Array.isArray(u.jammingFreq) ? u.jammingFreq.join(", ") : u.jammingFreq}</p>`;
        }
        
        if (u.unit_class === "RetransmiterUAV") {
          const btn = document.getElementById("toggleRtUavBtn");
          if (btn) {
            btn.addEventListener("click", () => {
              fetch("/toggle_uav_retransmitter", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  uav_id: u.id,
                  // flip it
                  active: !u.is_retransmitting
                })
              })
              .then(r => r.json())
              .then(d => {
                if (d.status === "ok") {
                  // reload units so the panel shows the new state
                  fetchUnits();
                } else {
                  alert(d.message || "Could not toggle retransmitter");
                }
              })
              .catch(console.error);
            });
          }
        }
        
    }
    
    function updateInfoPanelDynamic(u) {
      // this is only for panels that have the dynamic div
      const d = document.getElementById("unitInfoDynamic");
      if (!d) return;
    
      // fill only fast-changing stuff
      let html = "";
    
      // for retransmitter UAVs we care about battery, state and on/off
      if (u.unit_class === "RetransmiterUAV") {
        html += `<p>Battery: ${u.currentBattery ?? "?"}%</p>`;
        html += `<p>State: ${u.state ?? "?"}</p>`;
        html += `<p>Retransmitting: ${u.is_retransmitting ? "yes" : "no"}</p>`;
      }
    
      d.innerHTML = html;
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

        if (u.destination && Array.isArray(u.destination) && u.destination.length === 2) {
          const [dx, dy] = u.destination;
          const dist = Math.hypot(dx - u.x, dy - u.y);
          if (dist > 2) {
            ctx.save();
            ctx.beginPath();
            ctx.moveTo(u.x, u.y);
            ctx.lineTo(dx, dy);
            ctx.strokeStyle = "rgba(0, 160, 255, 0.6)";
            ctx.lineWidth = 2;
            ctx.setLineDash([6, 4]);
            ctx.stroke();
            ctx.restore();
          }
        }
        
                // draw future queued waypoints, if any
        if (Array.isArray(u.move_queue) && u.move_queue.length > 0) {
          ctx.save();
          ctx.beginPath();
        
          // start from the end of the currently drawn segment,
          // or from unit position if there's no current destination
          let lastX = u.x;
          let lastY = u.y;
        
          if (u.destination && Array.isArray(u.destination) && u.destination.length === 2) {
            lastX = u.destination[0];
            lastY = u.destination[1];
          }
        
          ctx.moveTo(lastX, lastY);
        
          for (const pt of u.move_queue) {
            // pt is [x, y]
            ctx.lineTo(pt[0], pt[1]);
            // optionally draw a small marker at each queued point
            // ctx.moveTo(pt[0], pt[1]);
          }
        
          // make it a bit lighter than the current segment so you can tell the difference
          ctx.strokeStyle = "rgba(0, 160, 255, 0.35)";
          ctx.lineWidth = 2;
          ctx.setLineDash([3, 3]);
          ctx.stroke();
          ctx.restore();
        }

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

        if (u.unit_class === "AntiAir" && u.aa_target && Array.isArray(u.aa_target)) {
          const [tx, ty] = u.aa_target;
          // draw only if the target is not exactly on top (to avoid tiny line)
          const dist = Math.hypot(tx - u.x, ty - u.y);
          if (dist > 2) {
            ctx.save();
            ctx.beginPath();
            ctx.moveTo(u.x, u.y);
            ctx.lineTo(tx, ty);
            ctx.strokeStyle = "rgba(255, 0, 0, 0.8)"; // red
            ctx.lineWidth = 2;
            ctx.setLineDash([]); // solid
            ctx.stroke();
            ctx.restore();
          }
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
        
        if (
          showTransmission &&
          u.unit_class === "RetransmiterUAV" &&
          u.is_retransmitting &&
          u.transmissionRange &&
          u.player === localPlayer  // keep it consistent with how you show friendly ranges
        ) {
          ctx.beginPath();
          ctx.arc(u.x, u.y, u.transmissionRange, 0, Math.PI * 2);
          ctx.strokeStyle = "rgba(0, 200, 0, 0.6)";
          ctx.lineWidth = 2;
          ctx.stroke();
          ctx.fillStyle = "rgba(0, 200, 0, 0.05)";
          ctx.fill();
        }

        // draw unit/base icon
        const img = u._img;
        if (img && img.complete) {
          ctx.drawImage(img, u.x - half, u.y - half, size, size);
          ctx.save();
          ctx.globalAlpha = 0.35;
          ctx.restore();
        } else {
          ctx.beginPath();
          ctx.arc(u.x, u.y, half, 0, Math.PI * 2);
        }
        
        if (u.unit_class === "AntiAir" && typeof u.ammo !== "undefined") {
          ctx.save();
          ctx.fillStyle = "red";
          ctx.font = "14px sans-serif";
          ctx.textAlign = "center";
          // a little above the unit icon
          ctx.fillText(u.ammo.toString(), u.x, u.y - half - 4);
          ctx.restore();
        }
        
        if (u.unit_class === "ElectronicWarfare" && showTransmission) {
          ctx.beginPath();
          ctx.arc(u.x, u.y, u.jammingRange, 0, Math.PI * 2);
          ctx.strokeStyle = "rgba(200,0,0,0.6)";
          ctx.lineWidth = 2;
          ctx.stroke();
          ctx.fillStyle = "rgba(200,0,0,0.05)";
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
    setInterval(fetchUnits, 200)
    window.requestAnimationFrame(gameLoop);
  </script>
</body>
</html>
"""

selected_unit_id = None  # server-side info about selection

SIM_PAUSED = False

#units = [UAVUnits.LoiteringMunition("Termopile", 50, 55, UAVUnits.UnitState.Landed, (100,100), "static/ICONS/UAV ALLY.png", UAVUnits.ArmourType.Unarmored, 1,1.7,0.0083, 0.0138,1.0,UAVUnits.ExplosiveType.HEAT,[2400])]
units = []

#aaUnits = [AntiAirUnits.AntiAir("Wuefkin",20,0, UAVUnits.UnitState.Idle, (400,400), "static/ICONS/AIR DEF ENEMY.png", UAVUnits.ArmourType.LightArmour, 2, 150, 3, 1, 2, AntiAirUnits.AAStatus.Idle)]
aaUnits = []

#logBases = [LogHub.LogHub("14 Baza Logistyczna", (150,150), "static/ICONS/HQ_ALLY.png",1, 300)]
logBases = []

ground_retransmitters = []

ewarUnits = []

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
    all_units = units + aaUnits + logBases + ground_retransmitters + ewarUnits

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
            "size": 28,
            "viewRange":getattr(u, "viewRange", 180)
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
            if getattr(u, "destination", None) is not None:
                # convert tuple -> list for JSON
                data["destination"] = [u.destination[0], u.destination[1]]
            if hasattr(u, "move_queue") and u.move_queue:
                data["move_queue"] = [[pt[0], pt[1]] for pt in u.move_queue]
            else:
                data["move_queue"] = []

        if isinstance(u, UAVUnits.RetransmiterUAV):
            data.update({
                "transmissionRange": u.transmissionRange,
                "is_retransmitting": getattr(u, "is_retransmitting", False)
            })

        # extra fields for LoiteringMunition
        if isinstance(u, UAVUnits.LoiteringMunition):
            data.update({
                "payload": u.payload,
                "explosiveType": u.explosiveType.name,
            })

        if isinstance(u, GroundUnits.SupplyVehicle):
            data.update({
                "cargoType": u.cargoType.name,
                "cargoAmmount": u.cargoAmmount,
            })

        # extra fields for AntiAir
        if isinstance(u, AntiAirUnits.AntiAir):
            data.update({
                "state": u.state.name,
                "armourType": u.armourType.name if hasattr(u, "armourType") else None,
                "range": u.range,
                "aa_state": u.AAstate.name,
                "ammo": u.ammoCount,
                "ammoType": u.ammoType.name if hasattr(u, "ammoType") else None
            })
            if u.target is not None:
                data["aa_target"] = [u.target.positionX, u.target.positionY]
                data["aa_target_name"] = getattr(u.target, "name", "Unknown")
            else:
                data["aa_target"] = None
                data["aa_target_name"] = None

        # extra fields for LogHub (the bases)
        if isinstance(u, LogHub.LogHub):
            # turn enum-keyed dict into plain {name: amount}
            storage_dict = {}
            if getattr(u, "inStorage", None):
                for k, v in u.inStorage.items():
                    # k is SupplyType
                    storage_dict[k.name if hasattr(k, "name") else str(k)] = v

            data.update({
                "transmissionRange": u.transmissionRange,
                "available_retransmitters": getattr(u, "available_retransmitters", 0),
                "current_spawned_uavs": getattr(u, "current_spawned_uavs", 0),
                "max_spawned_uavs": getattr(u, "max_deployed_uavs", 5),
                "current_air_retransmitters": getattr(u, "current_air_retransmitters", 0),
                "max_air_retransmitters": getattr(u, "max_air_retransmitters", 2),
                "storage": storage_dict
            })

        if isinstance(u, LogHub.GroundRetransmitter):
            data.update({
                "transmissionRange": u.transmissionRange,
                "parent_base_id": u.parent_base_id
            })

        if isinstance(u, LogHub.ElectronicWarfare):
            data.update({
                "jammingRange": u.jammingRange,
                "jammingFreq": getattr(u, "jammingFreq", [])
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
    queue = bool(data.get("queue", False))

    for u in units:
        if u.id == unit_id and u.player == PLAYER1:

            if isinstance(u, UAVUnits.UAV):
                if not is_uav_in_comm(u, logBases, ground_retransmitters):
                    return jsonify({"status": "error", "message": "UAV out of transmission range"}), 400

            if queue:
                # make sure queue exists
                if not hasattr(u, "move_queue"):
                    u.move_queue = []

                # if unit is not moving right now, treat this as the first move
                if u.state != UAVUnits.UnitState.Moving or u.destination is None:
                    u.move_unit((x, y), clear_queue=False)
                    print(f"[SERVER] (queued-first) moving unit {unit_id} to ({x}, {y})")
                    return jsonify({"status": "ok", "unit_id": unit_id, "destination": (x, y), "queued": True})
                else:
                    # already moving -> append
                    u.move_queue.append((x, y))
                    print(f"[SERVER] Queued move for unit {unit_id} to ({x}, {y})")
                    return jsonify({"status": "ok", "unit_id": unit_id, "queued_destination": (x, y), "queued": True})

            # normal click (no queue): overwrite
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
        image="static/ICONS/ŁĄCZNOŚĆ ALLY.png",
        player=base.player,
        transmissionRange=200,
        parent_base_id=base_id
    )
    ground_retransmitters.append(retrans)

    # decrease available on the base
    base.available_retransmitters -= 1

    return jsonify({"status": "ok", "available": base.available_retransmitters})

@app.route("/admin_destroy", methods=["POST"])
def admin_destroy():
    data = request.get_json()
    target_id = data.get("id", None)

    if target_id is None:
        return jsonify({"status": "error", "message": "no id provided"}), 400

    global units, aaUnits, logBases, ground_retransmitters, ewarUnits

    # we will try to find it in every list
    lists = [
        ("UAV/air unit", units),
        ("AntiAir", aaUnits),
        ("LogHub", logBases),
        ("GroundRetransmitter", ground_retransmitters),
        ("ElectronicWarfare", ewarUnits),
    ]

    for (label, lst) in lists:
        for obj in list(lst):  # copy to allow removal
            if getattr(obj, "id", None) == target_id:
                # if it has a 'state' (UAVs, AA) -> mark destroyed
                if hasattr(obj, "state"):
                    obj.state = UAVUnits.UnitState.Destroyed
                    # the game loop already cleans destroyed UAVs/AA,
                    # but we can also filter here if you want immediate effect
                    if lst is units:
                        units = [u for u in units if u.state != UAVUnits.UnitState.Destroyed]
                    if lst is aaUnits:
                        aaUnits = [a for a in aaUnits if a.state != UAVUnits.UnitState.Destroyed]
                else:
                    # structures: just remove from list
                    lst.remove(obj)

                return jsonify({
                    "status": "ok",
                    "id": target_id,
                    "destroyed_class": label
                })

    return jsonify({"status": "error", "message": "object not found"}), 404


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
    max_uavs = getattr(base, "max_deployed_uavs", 5)
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
        image="static/ICONS/UAV ALLY.png",
        armourType=UAVUnits.ArmourType.Unarmored,
        player=base.player,
        currentWeight=1.7,
        idleBatteryDrainPerTick=0.0083,
        moveBatteryDrainPerTick=0.0138,
        payload=1.0,
        explosiveType=UAVUnits.ExplosiveType.HEAT,
        usedFrequencies=[2400]
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

@app.route("/toggle_pause", methods=["POST"])
def toggle_pause():
    global SIM_PAUSED
    SIM_PAUSED = not SIM_PAUSED
    return jsonify({"status": "ok", "paused": SIM_PAUSED})

@app.route("/spawn_retrans_uav", methods=["POST"])
def spawn_retrans_uav():
    data = request.get_json()
    base_id = data.get("base_id")
    target_x = data.get("x")
    target_y = data.get("y")

    base = next((b for b in logBases if b.id == base_id), None)
    if base is None:
        return jsonify({"status": "error", "message": "base not found"}), 404

    # quota: 2 per base (or whatever is in the base)
    current_air = getattr(base, "current_air_retransmitters", 0)
    max_air = getattr(base, "max_air_retransmitters", 2)
    if current_air >= max_air:
        return jsonify({"status": "error", "message": "this base has no retransmitting UAVs left"}), 400

    # create at base position
    ruav = UAVUnits.RetransmiterUAV(
        name=f"RT-UAV-{base.id}-{current_air+1}",
        chanceToHit=0,
        baseSpeed=55,
        state=UAVUnits.UnitState.Idle,
        position=(base.positionX, base.positionY),
        image="static/ICONS/ROTOR ALLY.png",
        armourType=UAVUnits.ArmourType.Unarmored,
        player=base.player,
        currentWeight=1.7,
        idleBatteryDrainPerTick=0.0083,
        moveBatteryDrainPerTick=0.0138,
        transmissionRange=200.0,
        usedFrequencies=[5600]
    )

    # remember parent base if you want later reclamation
    ruav.parent_base_id = base.id

    # optionally send it to user’s click
    if target_x is not None and target_y is not None:
        ruav.move_unit((target_x, target_y))

    units.append(ruav)

    # consume slot
    base.current_air_retransmitters = current_air + 1

    return jsonify({"status": "ok", "uav_id": ruav.id})


@app.route("/toggle_uav_retransmitter", methods=["POST"])
def toggle_uav_retransmitter():
    data = request.get_json()
    uav_id = data.get("uav_id")
    active = bool(data.get("active", True))

    # find the UAV
    uav = next(
        (u for u in units
         if getattr(u, "id", None) == uav_id and isinstance(u, UAVUnits.RetransmiterUAV)),
        None
    )
    if uav is None:
        return jsonify({"status": "error", "message": "retransmitter UAV not found"}), 404

    uav.is_retransmitting = active
    return jsonify({"status": "ok", "active": uav.is_retransmitting})

@app.route("/admin_add_supply", methods=["POST"])
def admin_add_supply():
    data = request.get_json()
    base_id = data.get("base_id")
    supply_type = data.get("supply_type")
    amount = int(data.get("amount", 0))

    if base_id is None or supply_type is None:
        return jsonify({"status": "error", "message": "base_id and supply_type required"}), 400

    # find the LogHub
    base = next((b for b in logBases if b.id == base_id), None)
    if base is None:
        return jsonify({"status": "error", "message": "LogHub not found"}), 404

    # validate supply type
    try:
        st_enum = LogHub.SupplyType[supply_type]
    except KeyError:
        return jsonify({"status": "error", "message": f"Unknown supply type: {supply_type}"}), 400

    if amount <= 0:
        return jsonify({"status": "error", "message": "amount must be > 0"}), 400

    # make sure storage dict exists
    if getattr(base, "inStorage", None) is None:
        base.inStorage = {}

    current = base.inStorage.get(st_enum, 0)
    base.inStorage[st_enum] = current + amount

    # return fresh storage as plain dict
    storage_dict = {k.name: v for k, v in base.inStorage.items()}
    return jsonify({
        "status": "ok",
        "base_id": base.id,
        "storage": storage_dict
    })


@app.route("/admin_spawn", methods=["POST"])
def admin_spawn():
    data = request.get_json()
    unit_type = data.get("unit_type")      # e.g. "LoiteringMunition", "AntiAir", "LogHub", "GroundRetransmitter"
    player = int(data.get("player", 1))
    x = float(data.get("x"))
    y = float(data.get("y"))

    global units, aaUnits, logBases, ground_retransmitters

    if unit_type == "LoiteringMunition":
        if player == 1:
            img = "static/ICONS/UAV ALLY.png"
        else:
            img = "static/ICONS/UAV ENEMY.png"
        lm = UAVUnits.LoiteringMunition(
            name=f"LM-admin-{len(units)}",
            chanceToHit=50,
            baseSpeed=55,
            state=UAVUnits.UnitState.Landed,
            position=(x, y),
            image=img,
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
        if player == 1:
            img = "static/ICONS/AIR DEF ALLY.png"
        else:
            img = "static/ICONS/AIR DEF ENEMY.png"
        aa = AntiAirUnits.AntiAir(
            name=f"AA-admin-{len(aaUnits)}",
            chanceToHit=35,
            baseSpeed=0,
            state=UAVUnits.UnitState.Idle,
            position=(x, y),
            image=img,
            armourType=UAVUnits.ArmourType.LightArmour,
            player=player,
            range=150,
            ammoCount=5,
            ammoType=LogHub.SupplyType.AAMunition,
            aimTime=1.0,
            timeBetweenShots=2.0,
            AAstate=AntiAirUnits.AAStatus.Idle
        )
        aaUnits.append(aa)
        return jsonify({"status": "ok", "spawned": "AntiAir"})

    elif unit_type == "LogHub":
        if player == 1:
            img = "static/ICONS/HQ_ALLY.png"
        else:
            img = "static/ICONS/HQ_ENEMY.png"
        base = LogHub.LogHub(
            name=f"Base-admin-{len(logBases)}",
            position=(x, y),
            image=img,
            player=player,
            transmissionRange=300
        )
        logBases.append(base)
        return jsonify({"status": "ok", "spawned": "LogHub", "id": base.id})

    elif unit_type == "GroundRetransmitter":
        if player == 1:
            img = "static/ICONS/ŁĄCZNOŚĆ ALLY.png"
        else:
            img = "static/ICONS/ŁĄCZNOŚĆ ENEMY.png"
        rt = LogHub.GroundRetransmitter(
            name=f"RT-admin-{len(ground_retransmitters)}",
            position=(x, y),
            image=img,
            player=player,
            transmissionRange=200,
            parent_base_id=-1
        )
        ground_retransmitters.append(rt)
        return jsonify({"status": "ok", "spawned": "GroundRetransmitter"})

    elif unit_type == "RetransmiterUAV":
        if player == 1:
            img = "static/ICONS/ROTOR ALLY.png"
        else:
            img = "static/ICONS/ROTOR ENEMY.png"

        ruav = UAVUnits.RetransmiterUAV(
            name=f"RT-UAV-admin-{len(units)}",
            chanceToHit=0,
            baseSpeed=55,
            state=UAVUnits.UnitState.Landed,
            position=(x, y),
            image=img,
            armourType=UAVUnits.ArmourType.Unarmored,
            player=player,
            currentWeight=1.7,
            idleBatteryDrainPerTick=0.0083,
            moveBatteryDrainPerTick=0.0138,
            transmissionRange=200.0,
            usedFrequencies=[5600]
        )
        units.append(ruav)
        return jsonify({"status": "ok", "spawned": "RetransmiterUAV", "id": ruav.id})

    elif unit_type == "ElectronicWarfare":
        if player == 1:
            img = "static/ICONS/ELECTRONIC WARFARE ALLY.png"
        else:
            img = "static/ICONS/ELECTRONIC WARFARE ENEMY.png"
        # default jammingRange and frequencies — adjust as you like
        jamming_range = int(data.get("jammingRange", 200))
        jamming_freq = data.get("jammingFreq", [2400, 5800])
        if isinstance(jamming_freq, str):
            # parse comma-separated string just in case
            jamming_freq = [float(s.strip()) for s in jamming_freq.split(",") if s.strip()]

        ew = LogHub.ElectronicWarfare(
            name=f"EW-admin-{len(ewarUnits)}",
            position=(x, y),
            image=img,
            player=player,
            jammingRange=jamming_range,
            jammingFreq=jamming_freq
        )
        ewarUnits.append(ew)
        return jsonify({"status": "ok", "spawned": "ElectronicWarfare"})

    else:
        return jsonify({"status": "error", "message": "unknown unit type"}), 400

def spawn_supply_vehicle(from_base: LogHub.LogHub,
                         target_unit,
                         supply_type: LogHub.SupplyType,
                         amount: int):
    # clamp to what base really has
    available = from_base.inStorage.get(supply_type, 0)
    if available <= 0:
        return None
    amount = min(amount, available)

    # reserve immediately (so 2 units don't over-allocate)
    from_base.inStorage[supply_type] = available - amount

    # choose icon by player (reuse what you have)
    if from_base.player == 1:
        image = "static/ICONS/HQ_ALLY.png"
    else:
        image = "static/ICONS/HQ_ENEMY.png"

    veh = GroundUnits.SupplyVehicle(
        name=f"SUP-{from_base.id}",
        chanceToHit=0,
        baseSpeed=40,   # ground speed, tune as needed
        state=UAVUnits.UnitState.Idle,
        position=(from_base.positionX, from_base.positionY),
        image=image,
        armourType=UAVUnits.ArmourType.Unarmored,
        player=from_base.player,
        cargoType=supply_type,
        cargoAmmount=amount,
        target_unit_id=getattr(target_unit, "id"),
        home_base_id=from_base.id
    )

    # send it to the unit
    veh.move_unit((target_unit.positionX, target_unit.positionY))

    # and put it into the main 'units' list so the loop ticks it
    units.append(veh)
    return veh


def find_nearest_loghub_with_supply(player: int,
                                    supply_type: LogHub.SupplyType,
                                    x: float,
                                    y: float):
    best_base = None
    best_dist = None
    for b in logBases:
        if b.player != player:
            continue
        storage = getattr(b, "inStorage", {}) or {}
        if storage.get(supply_type, 0) <= 0:
            continue
        dx = x - b.positionX
        dy = y - b.positionY
        dist = math.hypot(dx, dy)
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_base = b
    return best_base


def is_uav_in_comm(uav, bases, retransmitters):
    """
    Return True if UAV currently has comm (i.e. able to receive commands).
    Jammers (ewarUnits) can block comm even if friendly bases/retransmitters are in range.
    By default, ANY jammer (friendly or enemy) will block; to make only enemy jammers block,
    change `allow_same_player_jammer` to False.
    """
    # ---- FIRST: check if any jammer is actively jamming this UAV ----
    uav_freqs = getattr(uav, "usedFrequencies", []) or []
    if uav_freqs:
        for jammer in ewarUnits:
            # skip inactive jammers if you later add is_active flag:
            if getattr(jammer, "is_active", True) is False:
                continue

            dx = uav.positionX - jammer.positionX
            dy = uav.positionY - jammer.positionY
            dist = math.hypot(dx, dy)
            if dist <= jammer.jammingRange:
                jammer_freqs = getattr(jammer, "jammingFreq", []) or []
                # simple overlap test (exact membership)
                for f in uav_freqs:
                    if f in jammer_freqs:
                        # Option: only consider enemy jammers. Set to True to allow friendly jammers
                        allow_same_player_jammer = True
                        if not allow_same_player_jammer and jammer.player == uav.player:
                            # ignore same-player jammer
                            continue
                        # jammed: no comm available
                        return False

    # ---- THEN: check normal comm sources (bases, ground retransmitters, airborne retrans) ----
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

    # airborne retransmitters
    for other in units:
        if other is uav:
            continue
        if isinstance(other, UAVUnits.RetransmiterUAV) \
           and getattr(other, "is_retransmitting", False) \
           and other.player == uav.player:
            dx = uav.positionX - other.positionX
            dy = uav.positionY - other.positionY
            if math.hypot(dx, dy) <= other.transmissionRange:
                return True

    # nothing provides comm
    return False


def game_loop():
    dt = 1.0 / TICK_RATE
    global units, aaUnits, SIM_PAUSED, pending_attacks
    while True:
        if SIM_PAUSED:
            # just wait one tick and go again
            time.sleep(dt)
            continue

        # --- normal simulation below ---
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
            if aa.ammoCount <= 0 and not getattr(aa, "supplyRequested", False):
                # try to find a base with AA ammo
                base = find_nearest_loghub_with_supply(
                    aa.player,
                    aa.ammoType,
                    aa.positionX,
                    aa.positionY
                )
                if base is not None:
                    spawn_supply_vehicle(base, aa, aa.ammoType, amount=5)  # amount to deliver
                    aa.supplyRequested = True

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

        # --- supply vehicle logic ---
        for u in list(units):  # list() so we can remove safely
            if isinstance(u, GroundUnits.SupplyVehicle):
                if u.phase == "to_target":
                    # find the target
                    target = next((x for x in units + aaUnits + logBases
                                   if getattr(x, "id", None) == u.target_unit_id), None)
                    if target is None:
                        # target gone -> go back
                        home = next((b for b in logBases if b.id == u.home_base_id), None)
                        if home:
                            u.move_unit((home.positionX, home.positionY))
                            u.phase = "to_base"
                        else:
                            # no home, just despawn
                            units.remove(u)
                        continue

                    # are we close enough to deliver?
                    dx = target.positionX - u.positionX
                    dy = target.positionY - u.positionY
                    if math.hypot(dx, dy) < 5:   # delivery radius
                        # deliver
                        if hasattr(target, "ammoCount") and hasattr(target, "ammoType"):
                            # only deliver matching type
                            if target.ammoType == u.cargoType:
                                target.ammoCount += u.cargoAmmount
                                # allow next requests later
                                setattr(target, "supplyRequested", False)

                        # after delivering -> go home
                        home = next((b for b in logBases if b.id == u.home_base_id), None)
                        if home:
                            u.move_unit((home.positionX, home.positionY))
                            u.phase = "to_base"
                        else:
                            units.remove(u)

                elif u.phase == "to_base":
                    home = next((b for b in logBases if b.id == u.home_base_id), None)
                    if home is None:
                        units.remove(u)
                        continue
                    dx = home.positionX - u.positionX
                    dy = home.positionY - u.positionY
                    if math.hypot(dx, dy) < 5:
                        # arrived -> despawn
                        units.remove(u)


        units = [u for u in units if u.state != UAVUnits.UnitState.Destroyed]
        aaUnits = [aa for aa in aaUnits if aa.state != UAVUnits.UnitState.Destroyed]

        if len(units) != before_uav or len(aaUnits) != before_aa:
            print(f"[SERVER] Destroyed units removed: "
                  f"{before_uav - len(units)} UAVs, {before_aa - len(aaUnits)} AA units.")


threading.Thread(target=game_loop, daemon=True).start()

if __name__ == "__main__":
    # run: python app.py
    app.run(debug=False)
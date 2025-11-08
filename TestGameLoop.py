import threading
import time

from flask import Flask, request, send_file, render_template_string, jsonify
from io import BytesIO
from PIL import Image, ImageDraw
import UAVUnits

app = Flask(__name__)

MAP_WIDTH = 800
MAP_HEIGHT = 500
TICK_RATE = 10

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
          units.forEach(u => {
            const img = new Image();
            img.src = u.image;
            u._img = img;
          });
        })
        .catch(err => console.error("Failed to fetch units:", err));
    }

    canvas.addEventListener("click", (event) => {
      const rect = canvas.getBoundingClientRect();
      const scaleX = canvas.width / rect.width;
      const scaleY = canvas.height / rect.height;

      const clickX = (event.clientX - rect.left) * scaleX;
      const clickY = (event.clientY - rect.top)  * scaleY;

      console.log("Click at:", clickX, clickY, " (scaled) ", "Canvas rect:", rect, "scales:", scaleX, scaleY);

      // check if clicked on a unit → select it
      for (const u of units) {
        const size = u.size || 24;
        const half = size / 2;
        if (clickX >= u.x - half && clickX <= u.x + half &&
            clickY >= u.y - half && clickY <= u.y + half) {
          selectedUnitId = u.id;
          moveTarget = null;
          updateInfoPanel(u);
          return;
        }
      }

      // if click on empty space and a unit is selected → set target using that unit’s speed property
      if (selectedUnitId !== null) {
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

    function updateUnits(dt) {
      for (const u of units) {
        if (u.id === selectedUnitId && moveTarget) {
          const dx = moveTarget.x - u.x;
          const dy = moveTarget.y - u.y;
          const dist = Math.sqrt(dx*dx + dy*dy);
          const speed = u.speed || 100; // use unit’s speed property if present

          if (dist > 1) {
            const vx = (dx / dist) * speed * (dt / 1000);
            const vy = (dy / dist) * speed * (dt / 1000);
            u.x += vx;
            u.y += vy;
          } else {
            moveTarget = null;
          }

          if (u.id === selectedUnitId) {
            updateInfoPanel(u);
          }
        }
      }
    }

    function drawUnits() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      for (const u of units) {
        const img = u._img;
        const size = u.size || 24;
        const half = size / 2;

        if (img && img.complete) {
          ctx.drawImage(img, u.x - half, u.y - half, size, size);
        } else {
          ctx.beginPath();
          ctx.arc(u.x, u.y, half, 0, Math.PI*2);
          ctx.fillStyle = "gray";
          ctx.fill();
        }

        if (u.id === selectedUnitId) {
          ctx.beginPath();
          ctx.arc(u.x, u.y, half + 4, 0, Math.PI*2);
          ctx.strokeStyle = "red";
          ctx.lineWidth = 2;
          ctx.stroke();
        }
      }

      if (moveTarget) {
        ctx.beginPath();
        ctx.arc(moveTarget.x, moveTarget.y, 6, 0, Math.PI*2);
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

      updateUnits(dt);
      drawUnits();

      window.requestAnimationFrame(gameLoop);
    }

    // initialization
    fetchUnits();
    window.requestAnimationFrame(gameLoop);
  </script>
</body>
</html>


"""
selected_unit_id = None  # server-side info about selection

units = [UAVUnits.LoiteringMunition("Termopile", 50, 55, UAVUnits.UnitState.Landed, (100,100), "static/images/uav.png", UAVUnits.ArmourType.Unarmored, 1,1.7,0.0083, 0.0138,1.0,UAVUnits.ExplosiveType.HEAT)]

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
    for u in units:
        unit_data.append({
            "id": u.id,
            "name": u.name,
            "x": u.positionX,
            "y": u.positionY,
            "image": u.image,   # path to image (e.g. "static/images/drone.png")
            "state": u.state.name,
            "player": u.player
        })
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

def game_loop():
    dt = 1.0/TICK_RATE
    while True:
        for u in units:
            u.tick_unit(dt)
        time.sleep(dt)

threading.Thread(target=game_loop, daemon=True).start()

if __name__ == "__main__":
    # run: python app.py
    app.run(debug=True)
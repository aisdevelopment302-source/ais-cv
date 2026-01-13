#!/usr/bin/env python3
"""
Web-based Line Calibration Tool
================================
Adjust counting lines via web browser.

Run this script and open http://<pi-ip>:5000 in browser
"""

from flask import Flask, render_template_string, jsonify, request
import cv2
import numpy as np
import yaml
import base64
from pathlib import Path

app = Flask(__name__)
PROJECT_ROOT = Path(__file__).parent.parent

# State
state = {
    'lines': {
        'L1': {'start': [480, 225], 'end': [540, 215], 'color': [0, 255, 0]},
        'L2': {'start': [525, 280], 'end': [585, 270], 'color': [0, 255, 255]},
        'L3': {'start': [565, 335], 'end': [630, 325], 'color': [0, 0, 255]},
    },
    'arrow': {'start': [530, 215], 'end': [620, 330]},
    'image_path': str(PROJECT_ROOT / "data" / "plate_seq_3.jpg")
}

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Line Calibrator</title>
    <style>
        body { 
            font-family: Arial, sans-serif; 
            margin: 20px; 
            background: #1a1a1a; 
            color: #fff;
        }
        .container { display: flex; gap: 20px; }
        .image-container { position: relative; }
        #canvas { border: 2px solid #444; cursor: crosshair; }
        .controls { 
            background: #2a2a2a; 
            padding: 20px; 
            border-radius: 8px;
            min-width: 300px;
        }
        .control-group { margin-bottom: 20px; }
        h3 { color: #4CAF50; margin-top: 0; }
        button { 
            padding: 10px 15px; 
            margin: 3px; 
            cursor: pointer;
            background: #444;
            color: #fff;
            border: none;
            border-radius: 4px;
        }
        button:hover { background: #555; }
        button.selected { background: #4CAF50; }
        button.arrow-btn { font-size: 18px; width: 45px; height: 45px; }
        .line-select button.L1 { border-left: 4px solid #00ff00; }
        .line-select button.L2 { border-left: 4px solid #00ffff; }
        .line-select button.L3 { border-left: 4px solid #ff0000; }
        .line-select button.arrow { border-left: 4px solid #ffffff; }
        .coords { 
            font-family: monospace; 
            background: #333; 
            padding: 10px;
            border-radius: 4px;
            margin-top: 10px;
        }
        .status { 
            color: #4CAF50; 
            margin-top: 10px;
            font-style: italic;
        }
        .btn-group { display: flex; flex-wrap: wrap; gap: 5px; }
        .arrow-grid {
            display: grid;
            grid-template-columns: repeat(3, 50px);
            gap: 3px;
            justify-content: center;
        }
        .step-select { margin: 10px 0; }
        .step-select label { margin-right: 15px; }
    </style>
</head>
<body>
    <h1>🔧 Conveyor Line Calibrator</h1>
    <div class="container">
        <div class="image-container">
            <canvas id="canvas" width="704" height="576"></canvas>
        </div>
        <div class="controls">
            <div class="control-group">
                <h3>Select Line</h3>
                <div class="btn-group line-select">
                    <button class="L1" onclick="selectLine('L1')">L1 (Green)</button>
                    <button class="L2" onclick="selectLine('L2')">L2 (Yellow)</button>
                    <button class="L3" onclick="selectLine('L3')">L3 (Red)</button>
                    <button class="arrow" onclick="selectLine('arrow')">Arrow</button>
                </div>
            </div>
            
            <div class="control-group">
                <h3>Select Point</h3>
                <div class="btn-group">
                    <button id="btn-start" onclick="selectPoint('start')">Start Point</button>
                    <button id="btn-end" onclick="selectPoint('end')">End Point</button>
                </div>
            </div>
            
            <div class="control-group">
                <h3>Move Point</h3>
                <div class="step-select">
                    <label><input type="radio" name="step" value="1" checked> 1px</label>
                    <label><input type="radio" name="step" value="5"> 5px</label>
                    <label><input type="radio" name="step" value="10"> 10px</label>
                </div>
                <div class="arrow-grid">
                    <div></div>
                    <button class="arrow-btn" onclick="move(0,-1)">↑</button>
                    <div></div>
                    <button class="arrow-btn" onclick="move(-1,0)">←</button>
                    <button class="arrow-btn" onclick="move(0,0)">•</button>
                    <button class="arrow-btn" onclick="move(1,0)">→</button>
                    <div></div>
                    <button class="arrow-btn" onclick="move(0,1)">↓</button>
                    <div></div>
                </div>
            </div>
            
            <div class="control-group">
                <h3>Actions</h3>
                <div class="btn-group">
                    <button onclick="captureFrame()">📷 Capture</button>
                    <button onclick="saveConfig()">💾 Save</button>
                    <button onclick="printCoords()">📋 Print</button>
                </div>
            </div>
            
            <div class="coords" id="coords">
                Select a line to see coordinates
            </div>
            <div class="status" id="status"></div>
        </div>
    </div>
    
    <script>
        let canvas = document.getElementById('canvas');
        let ctx = canvas.getContext('2d');
        let img = new Image();
        let state = {{ state | safe }};
        let selectedLine = 'L1';
        let selectedPoint = 'start';
        
        function loadImage() {
            fetch('/get_image')
                .then(r => r.json())
                .then(data => {
                    img.onload = () => draw();
                    img.src = 'data:image/jpeg;base64,' + data.image;
                });
        }
        
        function draw() {
            ctx.drawImage(img, 0, 0);
            
            // Draw lines
            for (let key in state.lines) {
                let line = state.lines[key];
                let color = `rgb(${line.color[2]},${line.color[1]},${line.color[0]})`;
                
                ctx.beginPath();
                ctx.moveTo(line.start[0], line.start[1]);
                ctx.lineTo(line.end[0], line.end[1]);
                ctx.strokeStyle = color;
                ctx.lineWidth = key === selectedLine ? 4 : 2;
                ctx.stroke();
                
                // Points
                ctx.beginPath();
                ctx.arc(line.start[0], line.start[1], 6, 0, 2*Math.PI);
                ctx.fillStyle = color;
                ctx.fill();
                
                ctx.beginPath();
                ctx.arc(line.end[0], line.end[1], 6, 0, 2*Math.PI);
                ctx.fill();
                
                // Label
                ctx.fillStyle = color;
                ctx.font = '14px Arial';
                ctx.fillText(key, line.end[0]+8, line.end[1]+5);
            }
            
            // Draw arrow
            let arrow = state.arrow;
            ctx.beginPath();
            ctx.moveTo(arrow.start[0], arrow.start[1]);
            ctx.lineTo(arrow.end[0], arrow.end[1]);
            ctx.strokeStyle = selectedLine === 'arrow' ? '#ff00ff' : '#ffffff';
            ctx.lineWidth = selectedLine === 'arrow' ? 4 : 2;
            ctx.stroke();
            
            // Arrow head
            let angle = Math.atan2(arrow.end[1]-arrow.start[1], arrow.end[0]-arrow.start[0]);
            ctx.beginPath();
            ctx.moveTo(arrow.end[0], arrow.end[1]);
            ctx.lineTo(arrow.end[0]-15*Math.cos(angle-0.4), arrow.end[1]-15*Math.sin(angle-0.4));
            ctx.lineTo(arrow.end[0]-15*Math.cos(angle+0.4), arrow.end[1]-15*Math.sin(angle+0.4));
            ctx.closePath();
            ctx.fillStyle = selectedLine === 'arrow' ? '#ff00ff' : '#ffffff';
            ctx.fill();
            
            // Highlight selected point
            let selObj = selectedLine === 'arrow' ? state.arrow : state.lines[selectedLine];
            if (selObj) {
                let pt = selObj[selectedPoint];
                ctx.beginPath();
                ctx.arc(pt[0], pt[1], 12, 0, 2*Math.PI);
                ctx.strokeStyle = '#ffffff';
                ctx.lineWidth = 2;
                ctx.stroke();
            }
            
            updateCoords();
        }
        
        function selectLine(line) {
            selectedLine = line;
            document.querySelectorAll('.line-select button').forEach(b => b.classList.remove('selected'));
            document.querySelector('.line-select button.' + (line === 'arrow' ? 'arrow' : line)).classList.add('selected');
            draw();
        }
        
        function selectPoint(point) {
            selectedPoint = point;
            document.getElementById('btn-start').classList.toggle('selected', point === 'start');
            document.getElementById('btn-end').classList.toggle('selected', point === 'end');
            draw();
        }
        
        function getStep() {
            return parseInt(document.querySelector('input[name="step"]:checked').value);
        }
        
        function move(dx, dy) {
            let step = getStep();
            fetch('/move', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    line: selectedLine,
                    point: selectedPoint,
                    dx: dx * step,
                    dy: dy * step
                })
            })
            .then(r => r.json())
            .then(data => {
                state = data.state;
                draw();
            });
        }
        
        function updateCoords() {
            let html = '<strong>Current Coordinates:</strong><br>';
            for (let key in state.lines) {
                let line = state.lines[key];
                html += `${key}: (${line.start[0]},${line.start[1]}) → (${line.end[0]},${line.end[1]})<br>`;
            }
            html += `Arrow: (${state.arrow.start[0]},${state.arrow.start[1]}) → (${state.arrow.end[0]},${state.arrow.end[1]})`;
            document.getElementById('coords').innerHTML = html;
        }
        
        function captureFrame() {
            document.getElementById('status').textContent = 'Capturing...';
            fetch('/capture', {method: 'POST'})
                .then(r => r.json())
                .then(data => {
                    document.getElementById('status').textContent = data.message;
                    loadImage();
                });
        }
        
        function saveConfig() {
            fetch('/save', {method: 'POST'})
                .then(r => r.json())
                .then(data => {
                    document.getElementById('status').textContent = data.message;
                });
        }
        
        function printCoords() {
            let text = 'Line Coordinates:\\n';
            for (let key in state.lines) {
                let line = state.lines[key];
                text += `${key}: start=[${line.start}], end=[${line.end}]\\n`;
            }
            text += `Arrow: start=[${state.arrow.start}], end=[${state.arrow.end}]`;
            alert(text);
            console.log(text);
        }
        
        // Keyboard controls
        document.addEventListener('keydown', (e) => {
            let step = getStep();
            switch(e.key) {
                case 'ArrowUp': move(0, -1); e.preventDefault(); break;
                case 'ArrowDown': move(0, 1); e.preventDefault(); break;
                case 'ArrowLeft': move(-1, 0); e.preventDefault(); break;
                case 'ArrowRight': move(1, 0); e.preventDefault(); break;
                case '1': selectLine('L1'); break;
                case '2': selectLine('L2'); break;
                case '3': selectLine('L3'); break;
                case 'a': selectLine('arrow'); break;
                case 's': selectPoint('start'); break;
                case 'e': selectPoint('end'); break;
            }
        });
        
        // Click to set point
        canvas.addEventListener('click', (e) => {
            let rect = canvas.getBoundingClientRect();
            let x = Math.round(e.clientX - rect.left);
            let y = Math.round(e.clientY - rect.top);
            
            fetch('/set_point', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    line: selectedLine,
                    point: selectedPoint,
                    x: x,
                    y: y
                })
            })
            .then(r => r.json())
            .then(data => {
                state = data.state;
                draw();
            });
        });
        
        // Init
        selectLine('L1');
        selectPoint('start');
        loadImage();
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    import json
    return render_template_string(HTML_TEMPLATE, state=json.dumps(state))

@app.route('/get_image')
def get_image():
    frame = cv2.imread(state['image_path'])
    if frame is None:
        frame = np.zeros((576, 704, 3), dtype=np.uint8)
    _, buffer = cv2.imencode('.jpg', frame)
    img_base64 = base64.b64encode(buffer).decode('utf-8')
    return jsonify({'image': img_base64})

@app.route('/move', methods=['POST'])
def move():
    data = request.json
    line = data['line']
    point = data['point']
    dx = data['dx']
    dy = data['dy']
    
    if line == 'arrow':
        state['arrow'][point][0] += dx
        state['arrow'][point][1] += dy
    else:
        state['lines'][line][point][0] += dx
        state['lines'][line][point][1] += dy
    
    return jsonify({'state': state})

@app.route('/set_point', methods=['POST'])
def set_point():
    data = request.json
    line = data['line']
    point = data['point']
    x = data['x']
    y = data['y']
    
    if line == 'arrow':
        state['arrow'][point] = [x, y]
    else:
        state['lines'][line][point] = [x, y]
    
    return jsonify({'state': state})

@app.route('/capture', methods=['POST'])
def capture():
    try:
        config_path = PROJECT_ROOT / "config" / "settings.yaml"
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        rtsp_url = config['camera']['rtsp_url']
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        for _ in range(10):
            cap.grab()
        ret, frame = cap.read()
        cap.release()
        
        if ret:
            cv2.imwrite(state['image_path'], frame)
            return jsonify({'message': 'Frame captured successfully!'})
        else:
            return jsonify({'message': 'Failed to capture frame'})
    except Exception as e:
        return jsonify({'message': f'Error: {str(e)}'})

@app.route('/save', methods=['POST'])
def save():
    try:
        config_path = PROJECT_ROOT / "config" / "settings.yaml"
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        config['counting_lines'] = {
            'line1': {'start': state['lines']['L1']['start'], 'end': state['lines']['L1']['end']},
            'line2': {'start': state['lines']['L2']['start'], 'end': state['lines']['L2']['end']},
            'line3': {'start': state['lines']['L3']['start'], 'end': state['lines']['L3']['end']},
            'flow_direction': {'start': state['arrow']['start'], 'end': state['arrow']['end']}
        }
        
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        
        print("\nSaved coordinates:")
        for key, line in state['lines'].items():
            print(f"  {key}: start={line['start']}, end={line['end']}")
        print(f"  Arrow: start={state['arrow']['start']}, end={state['arrow']['end']}")
        
        return jsonify({'message': 'Configuration saved to settings.yaml!'})
    except Exception as e:
        return jsonify({'message': f'Error saving: {str(e)}'})

if __name__ == '__main__':
    print("\n" + "="*50)
    print("LINE CALIBRATION WEB TOOL")
    print("="*50)
    print("Open in browser: http://localhost:5000")
    print("Or from another device: http://<raspberry-pi-ip>:5000")
    print("\nControls:")
    print("  - Click on image to set point position")
    print("  - Use arrow buttons or keyboard arrows to fine-tune")
    print("  - Press 1/2/3/a to select line, s/e for start/end")
    print("="*50 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=False)

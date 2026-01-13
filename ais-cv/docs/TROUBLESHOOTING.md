# AIS-CV Troubleshooting Guide

## Quick Diagnostics

```bash
# Is service running?
sudo systemctl status ais-counter

# Recent logs
tail -50 data/logs/counter.log

# Recent errors
tail -50 data/logs/counter-error.log

# Camera accessible?
python -c "
import cv2
import yaml
with open('config/settings.yaml') as f:
    config = yaml.safe_load(f)
cap = cv2.VideoCapture(config['camera']['rtsp_url'])
print('OK' if cap.isOpened() else 'FAILED')
cap.release()
"

# Firebase connected?
python scripts/test_firebase.py
```

## Common Issues

### Camera Connection Issues

#### Symptom: "Failed to connect to camera stream"

**Causes & Solutions:**

1. **Wrong RTSP URL**
   ```bash
   # Test URL with ffprobe
   ffprobe -rtsp_transport tcp "rtsp://admin:pass@192.168.1.100:554/cam/realmonitor?channel=1&subtype=1" 2>&1 | head -5
   ```
   - Verify IP address, credentials, and channel number
   - Try sub stream (subtype=1) vs main stream (subtype=0)

2. **Network issues**
   ```bash
   # Check if NVR is reachable
   ping 192.168.1.100
   
   # Check RTSP port
   nc -zv 192.168.1.100 554
   ```

3. **NVR busy/overloaded**
   - Too many simultaneous streams
   - Reduce other clients accessing NVR
   - Use sub stream instead of main stream

4. **Authentication failed**
   - Verify username/password in NVR web interface
   - Check for special characters in password (may need URL encoding)

#### Symptom: "Frame read failed, retrying..."

**Causes & Solutions:**

1. **Stream timeout**
   - Increase `reconnect_delay_seconds` in config
   - Check network stability

2. **Buffer overflow**
   - Already using `CAP_PROP_BUFFERSIZE=1`
   - Reduce processing load

3. **NVR restart/reboot**
   - Service will auto-reconnect (configured)
   - Check NVR logs for issues

### Detection Issues

#### Symptom: Missing counts (CV count < actual)

**Causes & Solutions:**

1. **Threshold too high**
   ```yaml
   # In settings.yaml, try lowering:
   counting:
     luminosity_threshold: 130  # Was 150
   ```

2. **Lines too short**
   - Run calibration tool: `python scripts/calibrate_lines.py`
   - Extend lines to cover full piece path

3. **Pieces too fast**
   ```yaml
   # Reduce frame requirement:
   counting:
     min_consecutive_frames: 1  # Was 2
   ```

4. **Sequence timeout too short**
   ```yaml
   # Increase timeout:
   counting:
     sequence_timeout: 6.0  # Was 4.0
   ```

5. **Pieces too dim**
   - Check if pieces are cooling before reaching lines
   - Move lines closer to furnace

#### Symptom: Extra counts (CV count > actual)

**Causes & Solutions:**

1. **Double counting**
   - Lines too close together
   - Piece oscillating back and forth
   - Increase line spacing

2. **Noise triggers**
   ```yaml
   # Increase thresholds:
   counting:
     luminosity_threshold: 170  # Was 150
     min_bright_pixels: 120     # Was 80
     min_consecutive_frames: 3   # Was 2
   ```

3. **Reflections**
   - Reposition lines to avoid reflective surfaces
   - Add `min_travel_time` filter:
   ```yaml
   counting:
     min_travel_time: 0.5  # Was 0.2
   ```

#### Symptom: Phantom counts (counts with no piece)

**Causes & Solutions:**

1. **Ambient light changes**
   - Increase `luminosity_threshold`
   - Consider different day/night thresholds

2. **Camera noise**
   - Increase `min_consecutive_frames`
   - Check camera focus/exposure settings

3. **Sparks/debris**
   - Increase `min_bright_pixels`
   - These are typically small and brief

### Session Tracking Issues

#### Symptom: Incorrect RUN/BREAK durations

**Causes & Solutions:**

1. **Break threshold too short**
   ```yaml
   detection:
     break_threshold_seconds: 180  # Was 120
   ```

2. **Pieces counted but not detected as RUN**
   - Check if counts are reaching SessionManager
   - Verify Firebase sync is working

3. **Time drift**
   - Ensure system clock is accurate:
   ```bash
   timedatectl status
   sudo timedatectl set-ntp true
   ```

#### Symptom: Sessions not showing in Firebase

1. **Firebase not initialized**
   - Check `data/logs/counter.log` for Firebase errors
   - Verify service account file

2. **Network issues**
   - Check internet connectivity
   - Firebase writes are fire-and-forget (may queue)

### Firebase Issues

#### Symptom: "Failed to initialize Firebase"

1. **Missing service account**
   ```bash
   ls -la config/firebase-service-account.json
   ```

2. **Invalid JSON**
   ```bash
   python -c "import json; json.load(open('config/firebase-service-account.json'))"
   ```

3. **Wrong project**
   - Verify project_id in service account matches Firebase console

#### Symptom: "Permission denied" errors

1. Check Firestore security rules
2. Verify service account has correct role
3. Regenerate service account key

#### Symptom: Data not appearing in dashboard

1. Check `live/furnace` document exists in Firestore
2. Verify date field matches today's date
3. Check browser console for errors

### Service Issues

#### Symptom: Service won't start

```bash
# Check service status
sudo systemctl status ais-counter

# Check for errors
sudo journalctl -u ais-counter -n 50

# Verify paths in service file
cat /etc/systemd/system/ais-counter.service
```

Common fixes:
- Ensure Python path is correct in ExecStart
- Check working directory exists
- Verify user has permissions

#### Symptom: Service starts then stops

```bash
# Check exit code
sudo journalctl -u ais-counter | grep "Main process exited"

# Check Python errors
cat data/logs/counter-error.log
```

Common causes:
- Config file not found
- Missing dependencies
- Camera connection fails

#### Symptom: High CPU usage

1. Check process:
   ```bash
   top -p $(pgrep -f run_counter)
   ```

2. Possible causes:
   - Main stream instead of sub stream (higher resolution)
   - Too high FPS processing
   - Memory leak (check with `htop`)

3. Solutions:
   - Use sub stream (704x576)
   - Add sleep between frames
   - Restart service periodically (cron)

### Memory Issues

#### Symptom: "Killed" or OOM errors

1. Check memory:
   ```bash
   free -h
   ```

2. Solutions:
   - Clear old photos: `find data/photos -mtime +7 -delete`
   - Add swap: `sudo dphys-swapfile install`
   - Reduce photo retention

### Log Issues

#### Symptom: Logs filling up disk

1. Check disk usage:
   ```bash
   df -h
   du -sh data/logs data/photos
   ```

2. Clean old data:
   ```bash
   # Delete photos older than 7 days
   find data/photos -mtime +7 -delete
   
   # Truncate large logs
   > data/logs/counter.log
   ```

3. Add to crontab:
   ```bash
   0 0 * * * find /home/adityajain/AIS/ais-cv/data/photos -mtime +7 -delete
   ```

## Debug Mode

### Enable verbose logging

```bash
# Edit settings.yaml
logging:
  level: "DEBUG"

# Or run directly with verbose
python scripts/run_counter.py --test
```

### Capture debug frames

```python
# Add to run_counter.py for debugging
if status['L1']['triggered']:
    cv2.imwrite(f"debug/l1_{time.time()}.jpg", frame)
```

### Test individual components

```python
# Test stream
from src.stream import RTSPStream
stream = RTSPStream("rtsp://...")
print(stream.connect())

# Test detector
from src.counter import PlateCounter
counter = PlateCounter(lines_config, counting_config)
# Feed test frames...

# Test Firebase
from src.firebase_client import FirebaseClient
fb = FirebaseClient()
print(fb.initialize())
```

## Getting Help

### Information to Collect

When reporting issues, include:

1. **Logs**
   ```bash
   tail -100 data/logs/counter.log
   tail -50 data/logs/counter-error.log
   ```

2. **Configuration** (redact credentials!)
   ```bash
   cat config/settings.yaml | sed 's/password:.*/password: REDACTED/'
   ```

3. **System info**
   ```bash
   uname -a
   python --version
   pip freeze | grep -E "opencv|numpy|firebase"
   ```

4. **Service status**
   ```bash
   sudo systemctl status ais-counter
   sudo journalctl -u ais-counter -n 50
   ```

## Related Documentation

- [Architecture](ARCHITECTURE.md)
- [Configuration](CONFIGURATION.md)
- [Calibration](CALIBRATION.md)
- [Deployment](DEPLOYMENT.md)

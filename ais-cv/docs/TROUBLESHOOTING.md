# AIS-CV Troubleshooting Guide

## Quick Diagnostics

```bash
# Is mill stand counter service running?
sudo systemctl status ais-mill-counter

# Recent logs - mill counter
tail -50 data/logs/mill-counter.log
tail -50 data/logs/mill-counter-error.log

# Camera accessible? (Channel 2 = CAM-2 mill stand)
python -c "
import cv2
import yaml
with open('config/settings.yaml') as f:
    config = yaml.safe_load(f)
rtsp = config['counting_areas']['areas'][0]['camera_rtsp']
cap = cv2.VideoCapture(rtsp)
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
   # Test URL with ffprobe (NVR IP: 192.168.1.200)
   # Channel 2 = CAM-2 (mill stand)
   ffprobe -rtsp_transport tcp "rtsp://admin:pass@192.168.1.200:554/cam/realmonitor?channel=2&subtype=1" 2>&1 | head -5
   ```
   - Verify IP address, credentials, and channel number
   - Try sub stream (subtype=1) vs main stream (subtype=0)

2. **Network issues**
   ```bash
   # Check if NVR is reachable
   ping 192.168.1.200

   # Check RTSP port
   nc -zv 192.168.1.200 554
   ```

3. **NVR busy/overloaded**
   - The mill counter opens multiple streams simultaneously — the NVR must support concurrent sub-stream connections
   - Reduce other clients accessing NVR
   - Use sub stream instead of main stream

4. **Authentication failed**
   - Verify username/password in NVR web interface
   - Check for special characters in password (may need URL encoding)

#### Symptom: "Frame read failed, retrying..."

**Causes & Solutions:**

1. **Stream timeout**
   - Check network stability

2. **Buffer overflow**
   - Already using `CAP_PROP_BUFFERSIZE=1`
   - Reduce processing load

3. **NVR restart/reboot**
   - Service will auto-reconnect (configured)
   - Check NVR logs for issues

### Detection Issues

#### Symptom: Missing counts - mill counter (CV count < actual)

**Causes & Solutions:**

1. **Not enough views agreeing** (majority voting)
   ```yaml
   # In settings.yaml, lower votes required:
   mill_stand_lines:
     voting:
       min_stands_required: 1  # Was null (majority)
   ```

2. **Voting window too short**
   ```yaml
   mill_stand_lines:
     voting:
       window_seconds: 8.0  # Was 5.0
   ```

3. **Hot metal filter too aggressive**
   ```yaml
   mill_stand_lines:
     counting:
       hot_metal_filter_enabled: false  # Disable temporarily to diagnose
   ```

4. **Lines misaligned** — re-run `scripts/calibrate_mill_stand_master.py`

#### Symptom: Extra counts (CV count > actual)

**Causes & Solutions:**

1. **Double counting**
   - Lines too close together
   - Piece oscillating back and forth
   - Increase line spacing

2. **Noise triggers**
   ```yaml
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
   - Check `data/logs/mill-counter.log` for Firebase errors
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

#### Symptom: Mill stand data not appearing in dashboard

1. Check `live/mill_stand` document exists in Firestore
2. Check `daily/{today}` for a document with `camera: 'CAM-2'`
3. Verify `ais-mill-counter` service is running and Firebase-enabled

### Service Issues

#### Symptom: Service won't start

```bash
# Mill counter
sudo systemctl status ais-mill-counter
sudo journalctl -u ais-mill-counter -n 50
cat /etc/systemd/system/ais-mill-counter.service
```

Common fixes:
- Ensure Python path is correct in ExecStart
- Check working directory exists
- Verify user has permissions

#### Symptom: Service starts then stops

```bash
# Mill counter
sudo journalctl -u ais-mill-counter | grep "Main process exited"
cat data/logs/mill-counter-error.log
```

Common causes:
- Config file not found
- Missing dependencies
- Camera connection fails

#### Symptom: High CPU usage

1. Check processes:
   ```bash
   top -p $(pgrep -f run_mill_counter)
   ```

2. Possible causes:
   - Main stream instead of sub stream (higher resolution)
   - Mill counter opens 3 streams simultaneously — check NVR load
   - Memory leak (check with `htop`)

3. Solutions:
   - Use sub stream (704x576 or 1920x1080 sub for mill)
   - Restart services periodically (cron)

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
   > data/logs/mill-counter.log
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
python scripts/run_mill_counter.py --test
```

### Test individual components

```python
# Test stream
from src.stream import RTSPStream
stream = RTSPStream("rtsp://...")
print(stream.connect())

# Test mill counter
from src.mill_stand_multi_view_counter import MultiViewLineCounter
counter = MultiViewLineCounter(views_config, counting_config, voting_config)

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
   # For mill counter:
   tail -100 data/logs/mill-counter.log
   tail -50 data/logs/mill-counter-error.log
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
   sudo systemctl status ais-mill-counter
   sudo journalctl -u ais-mill-counter -n 50
   ```

## Related Documentation

- [Architecture](ARCHITECTURE.md)
- [Configuration](CONFIGURATION.md)
- [Calibration](CALIBRATION.md)
- [Deployment](DEPLOYMENT.md)

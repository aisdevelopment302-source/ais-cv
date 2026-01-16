#!/usr/bin/env python3
"""
AIS Plate Counter - Main Entry Point
=====================================
Counts hot plate pieces on the furnace conveyor.

Features:
- Counts pieces using 3-line detection
- Tracks RUN/BREAK sessions (5 min threshold)
- Pushes counts and sessions to Firebase
- Sessions pushed when they START, updated as they progress
- Auto-resets at midnight

Usage:
    python run_counter.py              # Run continuously
    python run_counter.py --duration 60  # Run for 60 seconds
    python run_counter.py --test       # Test mode with verbose output
    python run_counter.py --no-firebase  # Run without Firebase sync
"""

import cv2
import yaml
import time
import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from counter import PlateCounter
from session_manager import SessionManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(PROJECT_ROOT / 'data' / 'logs' / 'counter.log')
    ]
)
logger = logging.getLogger(__name__)


def load_config():
    config_path = PROJECT_ROOT / "config" / "settings.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def run_counter(duration=None, test_mode=False, save_photos=True, use_firebase=True):
    """Run the plate counter with session tracking."""
    config = load_config()
    
    # Initialize counter with config
    counter = PlateCounter(
        lines_config=config['counting_lines'],
        counting_config=config.get('counting', {})
    )
    
    # Initialize session manager (5 min = 300s break threshold)
    break_threshold = config.get('detection', {}).get('break_threshold_seconds', 300)
    session_manager = SessionManager(break_threshold_seconds=break_threshold)
    
    # Initialize Firebase client (optional)
    firebase = None
    if use_firebase:
        try:
            from firebase_client import get_firebase_client
            firebase = get_firebase_client()
            if firebase.initialize():
                logger.info("Firebase connected - counts will sync to cloud")
                
                # Try to restore last session (crash recovery)
                last_session = firebase.get_last_session()
                if session_manager.restore_session(last_session):
                    logger.info(f"Continuing existing {session_manager.status} session")
                else:
                    logger.info("Starting fresh (no active session to continue)")
                
                # Sync today's count from Firebase (for photo filenames)
                today_count = firebase.get_today_count()
                if today_count > 0:
                    counter.total_count = today_count
                    logger.info(f"Restored today's count: {today_count}")
            else:
                logger.warning("Firebase init failed - running in offline mode")
                firebase = None
        except ImportError as e:
            logger.warning(f"Firebase module not available: {e}")
            firebase = None
        except Exception as e:
            logger.warning(f"Firebase error: {e}")
            firebase = None
    
    # Connect to camera
    rtsp_url = config['camera']['rtsp_url']
    logger.info(f"Connecting to: {config['camera']['name']}")
    
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    
    if not cap.isOpened():
        logger.error("Failed to connect to camera")
        if firebase:
            firebase.update_status('OFFLINE')
        return None
    
    logger.info("Connected! Starting plate counter...")
    logger.info(f"Thresholds: brightness>{config['counting']['luminosity_threshold']}, "
                f"min_pixels>{config['counting']['min_bright_pixels']}")
    logger.info(f"Break detection after {break_threshold}s of no counts")
    
    start_time = time.time()
    frame_count = 0
    last_status_time = 0
    last_session_update = 0
    
    try:
        while True:
            # Check duration
            elapsed = time.time() - start_time
            if duration and elapsed >= duration:
                break
            
            # Check for date change (midnight reset)
            if session_manager.check_daily_reset():
                logger.info("Midnight reset - new day started")
                if firebase:
                    firebase.reset_daily_count()
                counter.total_count = 0
                counter.counted_pieces = []
            
            ret, frame = cap.read()
            if not ret:
                logger.warning("Frame read failed, retrying...")
                time.sleep(0.5)
                continue
            
            frame_count += 1
            
            # Process frame
            counted_piece, status = counter.process_frame(frame)
            
            # Handle piece counted
            if counted_piece:
                # Build confidence string for logging
                conf_str = "HIGH" if counted_piece.confidence >= 80 else "MEDIUM" if counted_piece.confidence >= 60 else "LOW"
                logger.info(f"*** PIECE #{counted_piece.count_id} COUNTED | "
                           f"Travel: {counted_piece.travel_time:.2f}s | "
                           f"Conf: {counted_piece.confidence:.0f}% ({conf_str}) | "
                           f"Total: {counter.total_count} ***")
                
                # Notify session manager with travel time for speed tracking
                result = session_manager.on_piece_counted(travel_time=counted_piece.travel_time)
                
                # Handle session transitions and updates
                if firebase:
                    # End previous BREAK session if transitioning
                    if result['session_to_end']:
                        firebase.end_session(result['session_to_end'])
                    
                    # Create new RUN session if starting
                    if result['session_to_create']:
                        firebase.create_session(result['session_to_create'])
                    
                    # Update existing RUN session with new count
                    if result['session_to_update']:
                        firebase.update_session(result['session_to_update'])
                
                # Save photo first (so we have filename)
                photo_filename = ""
                if save_photos:
                    photo_dir = PROJECT_ROOT / 'data' / 'photos'
                    photo_dir.mkdir(parents=True, exist_ok=True)
                    
                    overlay_frame = counter.draw_overlay(frame, status)
                    photo_filename = f"count_{counted_piece.count_id}_{datetime.now(IST).strftime('%Y%m%d_%H%M%S')}.jpg"
                    cv2.imwrite(str(photo_dir / photo_filename), overlay_frame)
                
                # Push count to Firebase with full metadata
                if firebase:
                    firebase.push_count({
                        'timestamp': datetime.now(IST),
                        'travel_time': counted_piece.travel_time,
                        'confidence': counted_piece.confidence,
                        'line_pixels': {
                            'L1': counted_piece.l1_max_pixels,
                            'L2': counted_piece.l2_max_pixels,
                            'L3': counted_piece.l3_max_pixels,
                        },
                        'line_frames': {
                            'L1': counted_piece.l1_frames,
                            'L2': counted_piece.l2_frames,
                            'L3': counted_piece.l3_frames,
                        },
                        'line_brightness': {
                            'L1': counted_piece.l1_avg_brightness,
                            'L2': counted_piece.l2_avg_brightness,
                            'L3': counted_piece.l3_avg_brightness,
                        },
                        'photo_filename': photo_filename,
                    }, {'run_minutes_since_last': result['run_minutes_since_last']})
                    
                    # Update live status with current session info
                    firebase.update_status('RUNNING', session_manager.get_current_session_dict())
            
            # Check for break (idle detection - 5 min threshold)
            break_result = session_manager.check_for_break()
            if break_result:
                logger.info(f"Break detected - no counts for {break_threshold}s")
                
                if firebase:
                    # End the RUN session
                    if break_result['session_to_end']:
                        firebase.end_session(break_result['session_to_end'])
                    
                    # Create new BREAK session
                    if break_result['session_to_create']:
                        firebase.create_session(break_result['session_to_create'])
                    
                    # Update live status
                    firebase.update_status('BREAK', session_manager.get_current_session_dict())
            
            # Periodic status update (every 30 seconds)
            current_time = time.time()
            if current_time - last_status_time >= 30:
                last_status_time = current_time
                daily_totals = session_manager.get_daily_totals()
                logger.info(f"Status: {counter.total_count} pieces | "
                           f"Run: {daily_totals['total_run_minutes']:.1f}min | "
                           f"Break: {daily_totals['total_break_minutes']:.1f}min | "
                           f"State: {session_manager.status}")
            
            # Update Firebase status periodically (every 60 seconds)
            if firebase and current_time - last_session_update >= 60:
                last_session_update = current_time
                # Only update status, not session (duration updates at end only)
                firebase.update_status(session_manager.status, session_manager.get_current_session_dict())
            
            # Test mode: print every detection
            if test_mode:
                if any(status[l]['triggered'] for l in ['L1', 'L2', 'L3']):
                    ts = datetime.now(IST).strftime("%H:%M:%S")
                    l1 = f"{status['L1']['pixels']}px" if status['L1']['triggered'] else "-"
                    l2 = f"{status['L2']['pixels']}px" if status['L2']['triggered'] else "-"
                    l3 = f"{status['L3']['pixels']}px" if status['L3']['triggered'] else "-"
                    state = session_manager.status[:3]
                    print(f"{ts} | L1:{l1:>6} | L2:{l2:>6} | L3:{l3:>6} | Count:{status['total_count']} | {state}")
            
            time.sleep(0.05)  # ~20 FPS processing
            
    except KeyboardInterrupt:
        logger.info("Stopped by user")
    finally:
        cap.release()
        
        # End current session gracefully
        ended_session = session_manager.shutdown()
        if ended_session and firebase:
            firebase.end_session(ended_session)
        
        if firebase:
            firebase.update_status('OFFLINE')
    
    # Final stats
    stats = counter.get_stats()
    daily_totals = session_manager.get_daily_totals()
    
    logger.info("=" * 50)
    logger.info(f"FINAL COUNT: {stats['total_count']} pieces")
    if stats['total_count'] > 0:
        logger.info(f"Avg travel time: {stats['avg_travel_time']:.2f}s")
    logger.info(f"Total run time: {daily_totals['total_run_minutes']:.1f} minutes")
    logger.info(f"Total break time: {daily_totals['total_break_minutes']:.1f} minutes")
    logger.info(f"Runtime: {(time.time() - start_time)/60:.1f} minutes")
    logger.info("=" * 50)
    
    return stats


def main():
    parser = argparse.ArgumentParser(description='AIS Plate Counter')
    parser.add_argument('--duration', type=int, help='Run duration in seconds')
    parser.add_argument('--test', action='store_true', help='Test mode with verbose output')
    parser.add_argument('--no-photos', action='store_true', help='Disable photo capture')
    parser.add_argument('--no-firebase', action='store_true', help='Run without Firebase sync')
    args = parser.parse_args()
    
    run_counter(
        duration=args.duration,
        test_mode=args.test,
        save_photos=not args.no_photos,
        use_firebase=not args.no_firebase
    )


if __name__ == "__main__":
    main()

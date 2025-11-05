import os
import time
import json
import pickle
import logging
from collections import deque
from datetime import datetime

import cv2
import numpy as np
import face_recognition

import firebase_admin
from firebase_admin import credentials, db, storage

# ------------- Logging toggle -------------
DEBUG_LOGS = True
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
def log(msg):
    if DEBUG_LOGS:
        logging.info(msg)

# ------------- Firebase init -------------
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': "https://face-recognition-attenda-a3277-default-rtdb.firebaseio.com/",
    'storageBucket': "face-recognition-attenda-a3277.firebasestorage.app"
})
bucket = storage.bucket()

# ------------- Camera setup -------------
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# ------------- UI assets -------------
imgBackground = cv2.imread('Resources/background.png')

# Load mode images sorted numerically: 1.png=active, 2.png=info
folderModePath = 'Resources/Modes'
modePathList = sorted(os.listdir(folderModePath), key=lambda p: int(os.path.splitext(p)[0]) if os.path.splitext(p)[0].isdigit() else p)
imgModeList = [cv2.imread(os.path.join(folderModePath, p)) for p in modePathList]

IDX_ACTIVE = 0   # 1.png
IDX_INFO   = 1   # 2.png

# ------------- Encodings -------------
print("Loading Encode File ...")
with open('EncodeFile.p', 'rb') as f:
    encodeListKnown, studentIds = pickle.load(f)
print("Encode File Loaded")

# ------------- Timing & rotation -------------
# Non-blocking; we rely on time not waitKey for timing.
try:
    fps = int(cap.get(cv2.CAP_PROP_FPS)) or 30
except Exception:
    fps = 30
INFO_ROTATE_SECONDS = 0.2   # rotate the shown info every 0.2s when multiple faces present
IDLE_TO_ACTIVE_SECONDS = 5  # if no faces seen for 5s -> active

# ------------- State for rotation/queue -------------
last_face_time = 0.0
last_rotate_time = 0.0
display_queue = deque()    # deque of unique IDs currently to display
current_display_id = None
seen_ids_this_frame = set()

# ------------- Caches -------------
student_cache = {}  # id -> {'info': dict, 'img': np.ndarray or None}
already_marked_today_cache = {}  # id -> bool for today's date
session_marked = set()  # ids we have marked during this app session (safety)

def load_student_info_and_image(student_id):
    if student_id in student_cache:
        return student_cache[student_id]['info'], student_cache[student_id]['img']
    info = db.reference(f'Students/{student_id}').get()
    img = None
    try:
        blob = bucket.get_blob(f'Images/{student_id}.png')
        if blob:
            array = np.frombuffer(blob.download_as_string(), np.uint8)
            img = cv2.imdecode(array, cv2.IMREAD_COLOR)
    except Exception as e:
        logging.warning(f"Could not load image for {student_id}: {e}")
    student_cache[student_id] = {'info': info or {}, 'img': img}
    return student_cache[student_id]['info'], student_cache[student_id]['img']

def already_marked_today(student_id, info=None):
    today = datetime.now().strftime("%Y-%m-%d")
    cached = already_marked_today_cache.get(student_id)
    if cached is not None:
        return cached
    if info is None:
        info = db.reference(f'Students/{student_id}').get() or {}
    last = info.get('last_attendance_time', '')
    last_date = last.split(' ')[0] if last else ''
    res = (last_date == today)
    already_marked_today_cache[student_id] = res
    return res

def mark_attendance_if_needed(student_id):
    # Only once per day; and also guard with session_marked
    if student_id in session_marked and already_marked_today_cache.get(student_id, False):
        return
    # Ensure info cached
    info, _ = load_student_info_and_image(student_id)
    if already_marked_today(student_id, info):
        return
    try:
        ref = db.reference(f'Students/{student_id}')
        # Refresh info before write
        info = ref.get() or {}
        total_before = int(info.get('total_attendance', 0))
        total = total_before + 1
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ref.child('total_attendance').set(total)
        ref.child('last_attendance_time').set(now_str)
        # Update local caches
        already_marked_today_cache[student_id] = True
        session_marked.add(student_id)
        if student_id in student_cache:
            student_cache[student_id]['info']['total_attendance'] = total
            student_cache[student_id]['info']['last_attendance_time'] = now_str
        log(f"Marked attendance for id={student_id}: {total_before} -> {total} at {now_str}")
    except Exception as e:
        logging.error(f"Failed to mark attendance for {student_id}: {e}")

def update_display_queue(visible_ids):
    # Keep order: add new ids to the right if not already present
    existing = set(display_queue)
    for sid in visible_ids:
        if sid not in existing:
            display_queue.append(sid)
            existing.add(sid)
    # Remove ids no longer visible to keep the queue focused
    to_remove = [sid for sid in list(display_queue) if sid not in visible_ids]
    for sid in to_remove:
        try:
            display_queue.remove(sid)
        except ValueError:
            pass

def pick_current_display_id(now_ts):
    global current_display_id, last_rotate_time
    if not display_queue:
        return None
    # Rotate every INFO_ROTATE_SECONDS
    if (now_ts - last_rotate_time) >= INFO_ROTATE_SECONDS or current_display_id not in display_queue:
        display_queue.rotate(-1)  # move left; next becomes front
        current_display_id = display_queue[0]
        last_rotate_time = now_ts
    return current_display_id

while True:
    success, img = cap.read()
    if not success:
        log("Camera frame grab failed; exiting loop.")
        break

    # Compose background
    imgBackground[162:162 + 480, 55:55 + 640] = img

    # Detect faces at 1/4 size
    imgS = cv2.resize(img, (0, 0), None, 0.25, 0.25)
    imgS = cv2.cvtColor(imgS, cv2.COLOR_BGR2RGB)

    face_locations = face_recognition.face_locations(imgS)
    encodings = face_recognition.face_encodings(imgS, face_locations)

    now = time.time()
    visible_ids = []
    seen_ids_this_frame.clear()

    # Match each face to known encodings
    for enc in encodings:
        matches = face_recognition.compare_faces(encodeListKnown, enc)
        faceDis = face_recognition.face_distance(encodeListKnown, enc)
        matchIndex = np.argmin(faceDis) if len(faceDis) else None
        if matchIndex is not None and matches[matchIndex]:
            sid = studentIds[matchIndex]
            if sid not in seen_ids_this_frame:
                visible_ids.append(sid)
                seen_ids_this_frame.add(sid)
                # Mark attendance if needed (once per day)
                mark_attendance_if_needed(sid)

    if visible_ids:
        last_face_time = now
        # Update UI panel to INFO and queue
        imgBackground[44:44 + 633, 808:808 + 414] = imgModeList[IDX_INFO]
        update_display_queue(visible_ids)
        sid_to_show = pick_current_display_id(now)
    else:
        # No faces this frame
        sid_to_show = current_display_id if (now - last_face_time) < IDLE_TO_ACTIVE_SECONDS else None
        if sid_to_show is None:
            # Go to ACTIVE if idle for 5s
            imgBackground[44:44 + 633, 808:808 + 414] = imgModeList[IDX_ACTIVE]
            display_queue.clear()
            current_display_id = None
        else:
            # Keep showing INFO for the last person until idle timeout
            imgBackground[44:44 + 633, 808:808 + 414] = imgModeList[IDX_INFO]

    # Render info panel for the current person (if any)
    if sid_to_show is not None:
        info, imgStudent = load_student_info_and_image(sid_to_show)
        # Draw text fields onto the info panel area
        # total_attendance
        cv2.putText(imgBackground, str(info.get('total_attendance', '')), (861, 125),
                    cv2.FONT_HERSHEY_COMPLEX, 1, (255, 255, 255), 1)
        # major
        cv2.putText(imgBackground, str(info.get('major', '')), (1006, 550),
                    cv2.FONT_HERSHEY_COMPLEX, 0.5, (255, 255, 255), 1)
        # id
        cv2.putText(imgBackground, str(sid_to_show), (1006, 493),
                    cv2.FONT_HERSHEY_COMPLEX, 0.5, (255, 255, 255), 1)
        # standing / year / starting_year
        cv2.putText(imgBackground, str(info.get('standing', '')), (910, 625),
                    cv2.FONT_HERSHEY_COMPLEX, 0.6, (100, 100, 100), 1)
        cv2.putText(imgBackground, str(info.get('year', '')), (1025, 625),
                    cv2.FONT_HERSHEY_COMPLEX, 0.6, (100, 100, 100), 1)
        cv2.putText(imgBackground, str(info.get('starting_year', '')), (1125, 625),
                    cv2.FONT_HERSHEY_COMPLEX, 0.6, (100, 100, 100), 1)
        # name centered
        name = str(info.get('name', ''))
        (w, _), _ = cv2.getTextSize(name, cv2.FONT_HERSHEY_COMPLEX, 1, 1)
        offset = (414 - w) // 2
        cv2.putText(imgBackground, name, (808 + max(offset, 0), 445),
                    cv2.FONT_HERSHEY_COMPLEX, 1, (50, 50, 50), 1)
        # student image
        if imgStudent is not None:
            # Place inside the info card; adjust to your template
            img_resized = cv2.resize(imgStudent, (216, 216))
            imgBackground[175:175 + 216, 909:909 + 216] = img_resized

    # Show window (non-blocking). waitKey(1) only to allow UI refresh; not used for timing.
    cv2.imshow("Face Attendance", imgBackground)
    if cv2.waitKey(1) == 27:  # ESC to quit
        break

cap.release()
cv2.destroyAllWindows()
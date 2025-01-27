import numpy as np
import pandas as pd
import cv2
from queue import Queue

from deepface import DeepFace
from deepface.detectors import FaceDetector

import DeepFace_custom

FACE_DETECTOR_BACKEND = "opencv"

faces_df = pd.read_csv("../face_id_by_Alex/data_embeddings/data_embeddings_by_Facenet_rot.csv")
new_user_face_num = -1

from threading import Thread
from threading import Lock


def verify_face_name(img_1):
    try:
        img_embed = DeepFace_custom.to_embedding(img_1, model_name="Facenet")[0]["embedding"]
    except:
        return "UNDEFINED"
    user_name = "UNDEFINED"
    for face_name in set(faces_df["user"]):
        face_embeddings = faces_df[faces_df["user"] == face_name].drop(columns=["user"]).reset_index(drop=True)

        for face_inx in range(face_embeddings.shape[0]):
            face_embedding = np.array(face_embeddings.iloc[face_inx].values)

            if DeepFace_custom.veriby_by_embeddins(img_embed, face_embedding, model_name="Facenet"):
                user_name = face_name

    if user_name == "UNDEFINED":
        user_name = add_new_user(img_embed)

    return user_name


def add_new_user(user_face_emb):
    global new_user_face_num
    global faces_df

    if new_user_face_num == -1:
        set_user_names = set(faces_df["user"])
        max_inx = -1
        for un in set_user_names:
            if "USER_" in un:
                new_inx = int(un.split("_")[1])
                max_inx = new_inx if max_inx < new_inx else max_inx

        new_user_face_num = max_inx

    new_user_face_num += 1
    new_rec = pd.DataFrame()
    new_rec["user"] = [f"USER_{new_user_face_num}", ]
    for i in range(128):
        new_rec[f"p{i}"] = [user_face_emb[i], ]

    faces_df = pd.concat([faces_df, new_rec]).reset_index(drop=True)
    faces_df.to_csv("./data_embeddings/data_embeddings_by_Facenet_rot.csv", index=False)

    return f"USER_{new_user_face_num}"


def calculate_overlap_percentage(roi1, roi2):
    x1, y1, w1, h1 = roi1
    x2, y2, w2, h2 = roi2

    # Calculate intersection coordinates
    x_i = max(x1, x2)
    y_i = max(y1, y2)
    w_i = min(x1 + w1, x2 + w2) - x_i
    h_i = min(y1 + h1, y2 + h2) - y_i

    # Calculate area of overlap
    area_overlap = w_i * h_i

    # Calculate total areas
    area_roi1 = w1 * h1
    area_roi2 = w2 * h2

    return ((area_overlap / min(area_roi1, area_roi2)) + (area_overlap / max(area_roi1, area_roi2))) / 2


def get_tracker():
     return cv2.legacy.TrackerMOSSE_create


trackers_dict = dict()
frames_queue = Queue()
thread_lock = Lock()


def update_trackers_thread(lock):
    while True:
        detector = FaceDetector.build_model(FACE_DETECTOR_BACKEND)
        img_ = frames_queue.get()
        frames_queue.task_done()
        faces = FaceDetector.detect_faces(detector, FACE_DETECTOR_BACKEND, img_)

        for inx_, face_ in enumerate(faces):
            x, y, w, h = face_[1]
            roi_color = img_[y:y + h, x:x + w]

            tracker_face_overlap = 0
            with lock:
                for tr_obj in trackers_dict.values():
                    tfo = calculate_overlap_percentage((x, y, w, h), tr_obj[1])
                    tracker_face_overlap = tfo if tfo > tracker_face_overlap else tracker_face_overlap

            if tracker_face_overlap < 0.1:
                tracked_name = verify_face_name(roi_color)

                if tracked_name != "UNDEFINED":
                    tracker_obj = get_tracker()()
                    tracker_obj.init(img_, face_[1])
                    with lock:
                        trackers_dict[tracked_name] = [tracker_obj, (x, y, w, h)]
                    cv2.rectangle(img_, (x, y), (x + w, y + h), (255, 0, 0), 2)
                    break


frames_count = 0

font = cv2.FONT_HERSHEY_SIMPLEX
font_scale = 0.5
color = (165, 255, 0)
thickness = 2

tracker_update_thread = Thread(target=update_trackers_thread, args=(thread_lock, ))
tracker_update_thread.start()


def trace_detect_image(img):
    cv2.flip(img, 1)
    global frames_count, trackers_dict, thread_lock
    global font, font_scale, color, thickness

    if frames_count % 5 == 0:
        frames_queue.put(img)

    if trackers_dict:
        with thread_lock:
            for tracked_name in list(trackers_dict.keys()):
                tracker_obj = trackers_dict[tracked_name]
                tracked_res = tracker_obj[0].update(img)

                if tracked_res[0]:
                    x, y, w, h = tracked_res[1]
                    tracker_obj[1] = (x, y, w, h)
                    img = cv2.putText(img, tracked_name, (int(x), int(y) - 3), font, font_scale, color, thickness,
                                      cv2.LINE_AA)
                    cv2.rectangle(img, (int(x), int(y)), (int(x + w), int(y + h)), (255, 0, 0), 2)
                else:
                    del trackers_dict[tracked_name]
                    print("Loose tracker")

    frames_count += 1
    return img

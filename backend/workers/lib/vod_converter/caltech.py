"""
Ingestor for Caltech Pedestrian Detection Benchmark.

http://www.vision.caltech.edu/Image_Datasets/CaltechPedestrians/

Caltech dataset annotations:

Annotations are in json format:

{
    "set00": {
        "V000": {
            "altered": int
            "frames": {
                "0": {
                    0: {
                    "end": int, "hide": int, "id": int, "init": int, "lbl": label, "lock": int, "occl": int, "pos": [x, y, width, height], "posv": list, "str": int
                    }
                    1: {
                    "end": int, "hide": int, "id": int, "init": int, "lbl": label, "lock": int, "occl": int, "pos": [x, y, width, height], "posv": list, "str": int
                    }
                }
                "1": {
                    0: {
                    "end": int, "hide": int, "id": int, "init": int, "lbl": label, "lock": int, "occl": int, "pos": [x, y, width, height], "posv": list, "str": int
                    }
                }
            }
            "log": list
            "maxObj": int
            "nFrames": int (How many frames in video)
        }
    }

}


Labels:
person - individual pedestrian
people -  Large groups of pedes-trians for which it would have been tedious or impossible to label individuals
people? - assigned when clear identification of a pedestrian wasambiguous  or  easily  mistaken
person-fa - this label is quite the same as 'person?'
"""

import json
import os

from PIL import Image
from workers.lib.messenger import message

from .abstract import Ingestor
from .validation_schemas import get_blank_image_detection_schema, get_blank_detection_schema


class CaltechIngestor(Ingestor):
    def validate(self, path, folder_names):
        expected_dirs = [
            "images",
        ]
        for subdir in expected_dirs:
            if not os.path.isdir(os.path.join(path, subdir)):
                return False, f"Expected subdirectory {subdir} within {path}"
        if not os.path.isfile(os.path.join(path, "annotations.json")):
            return False, f"Expected annotations.json file within {path}"
        return True, None

    def ingest(self, path, folder_names):
        return self._get_image_detection(path, folder_names=folder_names)

    def _get_image_detection(self, root, folder_names):
        annotations = []
        failed_loads = 0
        path = os.path.join(root, "annotations.json")
        with open(path) as f:
            data = json.load(f)
            total_sets = len(data)
            sets_processed = 0
            for data_set_key, data_set_dict in data.items():
                video_processed = 0
                for video_key, video_dict in data_set_dict.items():
                    for frame_key, frame_dict in video_dict["frames"].items():
                        try:
                            single_img_detection = get_blank_image_detection_schema()

                            image_id = f"{data_set_key}_{video_key}_{frame_key}"
                            image_path = os.path.join(root, "images", f"{image_id}.png")
                            image_width, image_height = self._image_dimensions(image_path)

                            detections = self._get_detections(frame_dict, image_id, image_width, image_height)

                            single_img_detection["image"]["id"] = image_id
                            single_img_detection["image"]["dataset_id"] = None
                            single_img_detection["image"]["path"] = image_path
                            single_img_detection["image"]["segmented_path"] = None
                            single_img_detection["image"]["width"] = image_width
                            single_img_detection["image"]["height"] = image_height
                            single_img_detection["image"]["file_name"] = os.path.basename(image_path)

                            single_img_detection["detections"] = detections
                            annotations.append(single_img_detection)

                        except Exception as e:
                            message(e)
                            failed_loads += 1

                    video_processed += 1
                    message(f"Processed {video_processed} videos in current set")
                sets_processed += 1
                message(f"Loaded {sets_processed} sets on {total_sets}...")
        message(f"Unable to load {failed_loads} images")
        return annotations

    def _get_detections(self, frame, img_id, image_width, image_height):
        detections = []
        for i, annotation in enumerate(frame):
            curr_detection = get_blank_detection_schema()
            try:
                curr_detection["id"] = i
                curr_detection["image_id"] = img_id
                curr_detection["label"] = annotation["lbl"]
                curr_detection["segmentation"] = None
                curr_detection["left"] = annotation["pos"][0] if annotation["pos"][0] >= 0 else 0
                curr_detection["top"] = annotation["pos"][1] if annotation["pos"][1] >= 0 else 0
                curr_detection["right"] = annotation["pos"][0] + annotation["pos"][2] \
                    if annotation["pos"][0] + annotation["pos"][2] <= image_width else image_width
                curr_detection["bottom"] = annotation["pos"][1] + annotation["pos"][3] \
                    if annotation["pos"][1] + annotation["pos"][3] <= image_height else image_height
                curr_detection["iscrowd"] = False
                curr_detection["isbbox"] = True
                curr_detection["keypoints"] = []

                detections.append(curr_detection)
            except Exception as e:
                message(e)
        return detections

    @staticmethod
    def _image_dimensions(path):
        with Image.open(path) as image:
            return image.width, image.height

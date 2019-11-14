"""
csv file

photo_id|label|x1|y1|x2|y2

"""
import os
import pandas as pd
from PIL import Image

from .abstract import Ingestor, Egestor
from .validation_schemas import get_blank_detection_schema, get_blank_image_detection_schema

labels = {
    "pedestrian": "Pedestrian",
    "bicycle": "bicycle",
    "articulated_truck": "truck",
    "bus": "bus",
    "car": "car",
    "motorcycle": "motorcycle",
    "pickup_truck": "truck",
    "single_unit_truck": "truck",
    "work_van": "car",
    "motorized_vehicle": "car",
    "non-motorized_vehicle": "non_motorized_vehicle"}


class MIOIngestor(Ingestor):
    def validate(self, file_list, folder_names):
        if len(file_list) == 1 and '.csv' in file_list[0].filename:
            return True, None
        else:
            return False, None

    def ingest(self, path, folder_names):
        return self._get_image_detection(path, folder_names=folder_names)

    def _get_image_detection(self, file, folder_names):
        image_detection_schema = []
        image_detection_schema.append({'image': {'id': '00000000', 'file_name': 'temp'}, 'detections': {}})
        # try:
        df = pd.read_csv(file[0], dtype=str)
        last_id = '00000000'
        for index, row in df.iterrows():
            if len(image_detection_schema) % 50 == 1000: print(len(image_detection_schema))
            if int(image_detection_schema[-1]['image']['id']) < int(row['id']) and image_detection_schema[-1]['image'][
                'file_name'] != file_name:
                image_detection_schema.append({
                    'image': {
                        'id': image_id,
                        'path': image_path,
                        "dataset_id": 10,
                        'segmented_path': None,
                        'file_name': file_name,
                        'width': image_width,
                        'height': image_height
                    },
                    'detections': detections
                })
            detections = self._get_detections(row['id'], df)
            detections = [det for det in detections if
                          det['left'] < det['right'] and det['top'] < det['bottom']]
            image_id = row['id']
            image_path = f"{file}/train/{image_id}.jpg"
            file_name = f"{image_id}.jpg"
            image_width, image_height = 1920, 1080

        image_detection_schema.pop(0)
        return image_detection_schema

    # except Exception as e:
    # print(e)

    def _get_detections(self, id, df):
        detections = []
        sub_df = df.loc[df['id'] == id]
        for index, row in sub_df.iterrows():
            try:
                x1 = row['x1']
                y1 = row['y1']
                x2 = row['x2']
                y2 = row['y2']
                label = labels[row['label']]
                detections.append({
                    'label': label,
                    'left': int(x1),
                    'right': int(x2),
                    'top': int(y1),
                    'bottom': int(y2),
                    "iscrowd": False,
                    "isbbox": True,
                    "keypoints": [],
                    "segmentation": None

                })
            except ValueError as ve:
                print(row)
        return detections

    def _get_category(self, data, category_id):
        for category in data['categories']:
            if category['id'] == category_id:
                return category['name']

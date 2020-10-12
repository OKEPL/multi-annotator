from config import Config as AnnotatorConfig
from skimage.transform import resize
import imantics as im
import numpy as np
import cv2
from scipy.interpolate import interp1d
from scipy.ndimage import gaussian_filter
from keras.preprocessing.image import img_to_array
from mrcnn.config import Config
from .inference import ModelInferenceHandler
import logging

logger = logging.getLogger('gunicorn.error')

MODEL_DIR = AnnotatorConfig.MODEL_DIR
COCO_MODEL_PATH = AnnotatorConfig.MASK_RCNN_FILE
CLASS_NAMES = AnnotatorConfig.MASK_RCNN_CLASSES.split(',')
EXCLUDED_LAYERS = AnnotatorConfig.MASK_RCNN_EXCLUDED_LAYERS.split(',')


class CocoConfig(Config):
    """
    Configuration for COCO Dataset.
    """
    NAME = "coco"
    GPU_COUNT = 1
    IMAGES_PER_GPU = 1
    NUM_CLASSES = len(CLASS_NAMES)


class MaskRCNN():

    def __init__(self):
        self.config = CocoConfig()
        # self.model = modellib.MaskRCNN(
        #     mode="inference",
        #     model_dir=MODEL_DIR,
        #     config=self.config
        # )
        try:
            logger.info(f"Loading {COCO_MODEL_PATH}")
            self.model = ModelInferenceHandler(frozen_model_path=COCO_MODEL_PATH, output_type=0, max_batch_size=1)
            self.model.init_session()
            logger.info(f"Loaded MaskRCNN model: {COCO_MODEL_PATH}")
            logger.info("albert log test")

        except Exception as e:
            logger.error(e)
            logger.info("albert log test")
            logger.error(f"Could not load MaskRCNN model (place '{COCO_MODEL_PATH}' in the {MODEL_DIR} directory)")
            self.model = None

    def detect(self, image, image_model):
        logger.info("Started Detection xd")
        logger.info("New Log test")
        logger.info(COCO_MODEL_PATH)
        if self.model is None:
            return {}
        logger.info("Started Detection")
        image = image.convert('RGB')
        logger.info(image)
        width, height = image.size
        logger.info(width)

        # FOR DEBUG ONLY
        # image.thumbnail((1024, 1024))

        image = img_to_array(image)
        result = [self.model.predict(image, with_padding=False)]
        result = self.parse_result(result, width, height)
        bboxes = result["boxes"]
        segments = result["polygons"]
        class_ids = result["classes"]

        coco_image = im.Image(
            width=width, height=height,
            path=image_model.path,
            id=image_model.id,
            dataset=image_model.dataset_id
        )

        for bbox, segment, class_id in zip(bboxes, segments, class_ids):
            x1 = int(round(bbox[1] * width))
            y1 = int(round(bbox[2] * height))
            x2 = int(round(bbox[3] * width))
            y2 = int(round(bbox[0] * height))
            width_offset = x1
            height_offset = y2
            segment = self.points_interpolation(segment)
            for i in range(len(segment)):
                if i % 2 == 0:
                    segment[i] = segment[i]+width_offset
                else: segment[i] = height_offset + segment[i]
            fixed_mask = im.Polygons([segment])
            fixed_bbox = im.BBox((x1, y2, x2, y1))
            class_name = CLASS_NAMES[class_id - 1]
            category = im.Category(class_name)
            coco_image.add(fixed_mask, category=category)
            # comment this for no bbox label
            #coco_image.add(fixed_bbox, category=category)
        logger.info(coco_image.coco())
        return coco_image.coco()

    def parse_result(self, result, width, height):
        threshold = 0.4
        new_result = {"classes": [], "boxes": [], "scores": [], "polygons": []}
        classes = np.concatenate([el['detection_classes'] for el in result]).ravel().tolist()
        boxes = np.concatenate([el['detection_boxes'] for el in result]).ravel().tolist()
        scores = np.concatenate([el['detection_scores'] for el in result]).ravel().tolist()
        bin_masks = [np.where(r['detection_masks'] > threshold, 1, 0) for r in result if 'detection_masks' in r][0]

        for i in range(len(scores)):
            if scores[i] > threshold:
                new_result['classes'].append(classes[i])
                new_result['boxes'].append([boxes[i * 4], boxes[i * 4 + 1], boxes[i * 4 + 2], boxes[i * 4 + 3]])
                mask = cv2.resize(bin_masks[i].astype('float32'), (int((boxes[i*4+3]-boxes[i*4+1])*width),
                                                                   int((boxes[i*4+2]-boxes[i*4])*height)),
                                  interpolation=cv2.INTER_NEAREST)
                new_result['scores'].append(scores[i])
                if len(bin_masks) > i-1:
                    new_result['polygons'].append(im.Mask(mask).polygons().segmentation[0])
        return new_result

    @staticmethod
    def points_interpolation(segment):
        points = [[], []]
        for n in range(0, len(segment), 2):
            points[0].append(segment[n])
            points[1].append(segment[n+1])

        points = np.array([points[0], points[1]]).T
        distance = np.cumsum(np.sqrt(np.sum(np.diff(points, axis=0) ** 2, axis=1)))
        distance = np.insert(distance, 0, 0) / distance[-1]
        alpha = np.linspace(0, 1, 100)

        interpolator = interp1d(distance, points, kind='slinear', axis=0)
        interpolated_points = interpolator(alpha)
        interpolated_points = interpolated_points.flatten().tolist()
        return interpolated_points


model = MaskRCNN()
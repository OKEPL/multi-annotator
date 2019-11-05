# Copyright 2017 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

r"""Convert raw COCO dataset to TFRecord for object_detection.

Please note that this tool creates sharded output files.

Example usage:
    python create_coco_tf_record.py --logtostderr \
      --train_image_dir="${TRAIN_IMAGE_DIR}" \
      --train_annotations_file="${TRAIN_ANNOTATIONS_FILE}" \
      --output_dir="${OUTPUT_DIR}"
      --val_size = SIZE_OF_WANTED_VAL_DATASET
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import hashlib
import io
import json
import random
import os
import numpy as np
import PIL.Image

from pycocotools import mask
import tensorflow as tf

from workers.lib.tf_models import tf_record_creation_util
from workers.lib.tf_models import dataset_util
from workers.lib.tf_models import label_map_util
from workers.lib.tf_models import my_contextlib2 as contextlib2

# flags = tf.app.flags
# tf.flags.DEFINE_boolean('include_masks', False,
#                         'Whether to include instance segmentations masks '
#                         '(PNG encoded) in the result. default: False.')
# tf.flags.DEFINE_string('train_image_dir',
#                        '/home/bielinski/Desktop/Datasets/Pascal_voc/VOCtrainval_11-May-2012/VOCdevkit/VOC2012/JPEGImages',
#                        'Training image directory.')
# tf.flags.DEFINE_string('val_image_dir',
#                        '/home/bielinski/Desktop/Datasets/Pascal_voc/VOCtrainval_11-May-2012/VOCdevkit/VOC2012/JPEGImages',
#                        'Validation image directory.')
# tf.flags.DEFINE_string('test_image_dir', '',
#                        'Test image directory.')
# tf.flags.DEFINE_string('train_annotations_file',
#                        '/home/bielinski/Desktop/Datasets/Pascal_voc/coco_from_pascal/pascal_voc_from_my_annotator.json',
#                        'Training annotations JSON file.')
# tf.flags.DEFINE_string('val_annotations_file', '',
#                        'Validation annotations JSON file.')
# tf.flags.DEFINE_string('testdev_annotations_file', '',
#                        'Test-dev annotations JSON file.')
# tf.flags.DEFINE_string('output_dir', '/tmp/', 'Output data directory.')
# tf.flags.DEFINE_integer('val_size', 100, 'Size of validaton dataset')
#
# FLAGS = flags.FLAGS
#
# tf.logging.set_verbosity(tf.logging.INFO)


def create_tf_example(image,
                      annotations_list,
                      image_dir,
                      category_index,
                      include_masks=False):
    """Converts image and annotations to a tf.Example proto.

    Args:
      image: dict with keys:
        [u'license', u'file_name', u'coco_url', u'height', u'width',
        u'date_captured', u'flickr_url', u'id']
      annotations_list:
        list of dicts with keys:
        [u'segmentation', u'area', u'iscrowd', u'image_id',
        u'bbox', u'category_id', u'id']
        Notice that bounding box coordinates in the official COCO dataset are
        given as [x, y, width, height] tuples using absolute coordinates where
        x, y represent the top-left (0-indexed) corner.  This function converts
        to the format expected by the Tensorflow Object Detection API (which is
        which is [ymin, xmin, ymax, xmax] with coordinates normalized relative
        to image size).
      image_dir: directory containing the image files.
      category_index: a dict containing COCO category information keyed
        by the 'id' field of each category.  See the
        label_map_util.create_category_index function.
      include_masks: Whether to include instance segmentations masks
        (PNG encoded) in the result. default: False.
    Returns:
      example: The converted tf.Example
      num_annotations_skipped: Number of (invalid) annotations that were ignored.

    Raises:
      ValueError: if the image pointed to by data['filename'] is not a valid JPEG
    """
    image_height = image['height']
    image_width = image['width']
    filename = image['file_name']
    image_id = image['id']

    full_path = os.path.join(image_dir, filename)
    with tf.gfile.GFile(full_path, 'rb') as fid:
        encoded_jpg = fid.read()
    encoded_jpg_io = io.BytesIO(encoded_jpg)
    image = PIL.Image.open(encoded_jpg_io)
    key = hashlib.sha256(encoded_jpg).hexdigest()

    xmin = []
    xmax = []
    ymin = []
    ymax = []
    is_crowd = []
    category_names = []
    category_ids = []
    area = []
    encoded_mask_png = []
    num_annotations_skipped = 0
    for object_annotations in annotations_list:
        (x, y, width, height) = tuple(object_annotations['bbox'])
        if width <= 0 or height <= 0:
            num_annotations_skipped += 1
            continue
        if x + width > image_width or y + height > image_height:
            num_annotations_skipped += 1
            continue
        xmin.append(float(x) / image_width)
        xmax.append(float(x + width) / image_width)
        ymin.append(float(y) / image_height)
        ymax.append(float(y + height) / image_height)
        is_crowd.append(object_annotations['iscrowd'])
        category_id = int(object_annotations['category_id'])
        category_ids.append(category_id)
        category_names.append(category_index[category_id]['name'].encode('utf8'))
        area.append(object_annotations['area'])

        if include_masks:
            run_len_encoding = mask.frPyObjects(object_annotations['segmentation'],
                                                image_height, image_width)
            binary_mask = mask.decode(run_len_encoding)
            if not object_annotations['iscrowd']:
                binary_mask = np.amax(binary_mask, axis=2)
            pil_image = PIL.Image.fromarray(binary_mask)
            output_io = io.BytesIO()
            pil_image.save(output_io, format='PNG')
            encoded_mask_png.append(output_io.getvalue())
    feature_dict = {
        'image/height':
            dataset_util.int64_feature(image_height),
        'image/width':
            dataset_util.int64_feature(image_width),
        'image/filename':
            dataset_util.bytes_feature(filename.encode('utf8')),
        'image/source_id':
            dataset_util.bytes_feature(str(image_id).encode('utf8')),
        'image/key/sha256':
            dataset_util.bytes_feature(key.encode('utf8')),
        'image/encoded':
            dataset_util.bytes_feature(encoded_jpg),
        'image/format':
            dataset_util.bytes_feature('jpeg'.encode('utf8')),
        'image/object/bbox/xmin':
            dataset_util.float_list_feature(xmin),
        'image/object/bbox/xmax':
            dataset_util.float_list_feature(xmax),
        'image/object/bbox/ymin':
            dataset_util.float_list_feature(ymin),
        'image/object/bbox/ymax':
            dataset_util.float_list_feature(ymax),
        'image/object/class/text':
            dataset_util.bytes_list_feature(category_names),
        'image/object/is_crowd':
            dataset_util.int64_list_feature(is_crowd),
        'image/object/area':
            dataset_util.float_list_feature(area),
    }
    if include_masks:
        feature_dict['image/object/mask'] = (
            dataset_util.bytes_list_feature(encoded_mask_png))
    example = tf.train.Example(features=tf.train.Features(feature=feature_dict))
    return key, example, num_annotations_skipped


def _create_tf_record_from_coco_annotations(
        task, groundtruth_data, image_dir, output_path, include_masks, num_shards):
    """Loads COCO annotation json files and converts to tf.Record format.

    Args:
      groundtruth_data: JSON file containing bounding box annotations.
      image_dir: Directory containing the image files.
      output_path: Path to output tf.Record file.
      include_masks: Whether to include instance segmentations masks
        (PNG encoded) in the result. default: False.
      num_shards: number of output file shards.
    """
    # with contextlib2.ExitStack() as tf_record_close_stack, \
    # tf.gfile.GFile(annotations_file, 'r') as fid:
    with contextlib2.ExitStack() as tf_record_close_stack:
        output_tfrecords, results_paths = tf_record_creation_util.open_sharded_output_tfrecords(
            tf_record_close_stack, output_path, num_shards)
        # groundtruth_data = json.load(fid)
        images = groundtruth_data['images']
        category_index = label_map_util.create_category_index(
            groundtruth_data['categories'])

        annotations_index = {}
        if 'annotations' in groundtruth_data:
            task.info(
                'Found groundtruth annotations. Building annotations index.')
            for annotation in groundtruth_data['annotations']:
                image_id = annotation['image_id']
                if image_id not in annotations_index:
                    annotations_index[image_id] = []
                annotations_index[image_id].append(annotation)
        missing_annotation_count = 0
        for image in images:
            image_id = image['id']
            if image_id not in annotations_index:
                missing_annotation_count += 1
                annotations_index[image_id] = []
        task.info(f'{missing_annotation_count} images are missing annotations.')

        total_num_annotations_skipped = 0
        for idx, image in enumerate(images):
            if idx % 100 == 0:
                task.info(f'On image {idx} of {len(images)}')
            annotations_list = annotations_index[image['id']]
            _, tf_example, num_annotations_skipped = create_tf_example(
                image, annotations_list, image_dir, category_index, include_masks)
            total_num_annotations_skipped += num_annotations_skipped
            shard_idx = idx % num_shards
            output_tfrecords[shard_idx].write(tf_example.SerializeToString())
        task.info(f'Finished writing, skipped {total_num_annotations_skipped} annotations.')

    return results_paths


def _split_dataset(annotations_file, val_size):
    # TODO: Optimize
    groundtruth_data = json.loads(annotations_file)
    images = groundtruth_data['images']
    annotations = groundtruth_data['annotations']
    val_images = random.sample(images, val_size)
    val_image_ids = [image['id'] for image in val_images]
    images = [image for image in images if image not in val_images]
    val_annotations = [annotation for annotation in annotations if annotation['image_id'] in val_image_ids]
    annotations = [annotation for annotation in annotations if annotation not in val_annotations]
    train_data = {'images': images, 'categories': groundtruth_data['categories'], 'annotations': annotations}
    val_data = {'images': val_images, 'categories': groundtruth_data['categories'], 'annotations': val_annotations}
    return train_data, val_data


def convert_coco_to_tfrecord(image_dir, annotations_file, output_dir, val_size, task, include_masks=False):
    assert image_dir, '`image_dir` missing.'
    assert annotations_file, '`annotations_file` missing.'
    assert output_dir, '`output_dir` missing.'
    assert val_size, '`val_size` missing'

    if not tf.gfile.IsDirectory(output_dir):
        tf.gfile.MakeDirs(output_dir)
    train_output_path = os.path.join(output_dir, 'coco_train.record')
    val_output_path = os.path.join(output_dir, 'coco_val.record')
    # testdev_output_path = os.path.join(FLAGS.output_dir, 'coco_testdev.record')
    task.info("Splitting data into train and val sets")
    train_annotation, val_annotation = _split_dataset(annotations_file, val_size)

    task.info("Creating train set")
    results_paths_train = _create_tf_record_from_coco_annotations(
        task,
        train_annotation,
        image_dir,
        train_output_path,
        include_masks,
        num_shards=1)

    task.info("Creating val set")
    results_paths_val =_create_tf_record_from_coco_annotations(
        task,
        val_annotation,
        image_dir,
        val_output_path,
        include_masks,
        num_shards=1)


    """
    _create_tf_record_from_coco_annotations(
        FLAGS.testdev_annotations_file,
        FLAGS.test_image_dir,
        testdev_output_path,
        FLAGS.include_masks,
        num_shards=100)"""

    all_paths = results_paths_train + results_paths_val
    return all_paths

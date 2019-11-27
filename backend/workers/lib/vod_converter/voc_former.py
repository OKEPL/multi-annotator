"""
Ingestor and egestor for VOC formats.

http://host.robots.ox.ac.uk/pascal/VOC/voc2012/htmldoc/index.html
"""

import os
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from .abstract import Ingestor, Egestor
from .labels_and_aliases import output_labels


class VOCIngestor(Ingestor):

    iii =0

    def validate(self, root, folder_names):
        if folder_names is None:
            folder_names={'images': 'JPEGImages', 'annotations': "Annotations", "trainval": "ImageSets/Main"}
        path = f"{root}"
        print(root)
        for subdir in folder_names.values():
            if not os.path.isdir(os.path.join(root, subdir)):
                return False, f"Expected subdirectory {subdir}"
            if not os.path.isfile(os.path.join(path, os.path.join(folder_names['trainval'], 'trainval.txt' ))):
                return False, f"Expected main image set ImageSets/Main/trainval.txt to exist within {path}"
        return True, None

    def ingest(self, path, folder_names=None):
        if folder_names is None:
            folder_names={'images': 'JPEGImages', 'annotations': "Annotations", "trainval": "ImageSets/Main"}
        image_names = self._get_image_ids(path, folder_names)
        return [self._get_image_detection(path, image_name, folder_names) for image_name in image_names]

    def _get_image_ids(self, root, folder_names):
        if folder_names is None:
            path = f"{root}/ImageSets/mk/trainval.txt"
        else:
            path = os.path.join(os.path.join(root, os.path.join(folder_names['trainval'], 'trainval.txt' )))

        with open(path, 'r+') as f:
            lines = f.readlines()
            if len(lines) ==0:
                fnames = [Path(file).stem for file in os.listdir(folder_names['images'])]
                f.writelines(fnames)
            else:
                fnames = [x.replace('\n', '') for x in lines]
            return fnames

    def _get_image_detection(self, root, image_id, folder_names):
        print(self.iii)

        self.iii +=1
        path = f"{root}"
        image_path = os.path.join(os.path.join(root, os.path.join(folder_names['images'], f"{image_id}.jpg")))
        if not os.path.isfile(image_path):
            raise Exception(f"Expected {image_path} to exist.")
        annotation_path = os.path.join(os.path.join(root, os.path.join(folder_names['annotations'], f"{image_id}.xml")))
        if not os.path.isfile(annotation_path):
            raise Exception(f"Expected annotation file {annotation_path} to exist.")
        tree = ET.parse(annotation_path)
        xml_root = tree.getroot()
        size = xml_root.find('size')
        segmented = xml_root.find('segmented').text == '1'
        segmented_path = None
        if segmented:
            segmented_path = f"{path}/SegmentationObject/{image_id}.png"
            if not os.path.isfile(segmented_path):
                raise Exception(f"Expected segmentation file {segmented_path} to exist.")
        image_width = int(size.find('width').text)
        image_height = int(size.find('height').text)
        return {
            'image': {
                'id': image_id,
                'path': image_path,
                'segmented_path': segmented_path,
                'width': image_width,
                'height': image_height
            },
            'detections': [self._get_detection(node) for node in xml_root.findall('object')]
        }

    def _get_detection(self, node):
        bndbox = node.find('bndbox')
        return {
            'label': node.find('name').text,
            'top': float(bndbox.find('ymin').text) - 1,
            'left': float(bndbox.find('xmin').text) - 1,
            'right': float(bndbox.find('xmax').text) - 1,
            'bottom': float(bndbox.find('ymax').text) - 1,
        }


class VOCEgestor(Egestor):

    def expected_labels(self):
        return output_labels

    def egest(self, *, image_detections, root, folder_names):
        image_sets_path = f"{root}/ImageSets/Main"
        images_path = os.path.join(root, folder_names['images'])
        annotations_path = os.path.join(root, folder_names['annotations'])
        segmentations_path = f"{root}/SegmentationObject"
        segmentations_dir_created = False

        for to_create in [image_sets_path, images_path, annotations_path]:
            os.makedirs(to_create, exist_ok=True)
        for image_detection in image_detections:
            image = image_detection['image']
            image_id = image['id']
            src_extension = image['path'].split('.')[-1]
            shutil.copyfile(image['path'], f"{images_path}/{image_id}.{src_extension}")

            with open(f"{image_sets_path}/trainval.txt", 'a') as out_image_index_file:
                out_image_index_file.write(f'{image_id}\n')

            if image['segmented_path'] is not None:
                if not segmentations_dir_created:
                    os.makedirs(segmentations_path)
                    segmentations_dir_created = True
                shutil.copyfile(image['segmented_path'], f"{segmentations_path}/{image_id}.png")

            temp = root.split('/')[-1]
            xml_root = ET.Element('annotation')
            add_text_node(xml_root, 'filename', f"{image_id}.{src_extension}")
            add_text_node(xml_root, 'folder', root.split('/')[-1])
            add_text_node(xml_root, 'segmented', int(segmentations_dir_created))

            add_sub_node(xml_root, 'size', {
                'depth': 3,
                'width': image['width'],
                'height': image['height']
            })
            add_sub_node(xml_root, 'source', {
                'annotation': 'Dummy',
                'database': 'Dummy',
                'image': 'Dummy'
            })

            for detection in image_detection['detections']:
                x_object = add_sub_node(xml_root, 'object', {
                    'name': detection['label'],
                    'difficult': 0,
                    'occluded': 0,
                    'truncated': 0,
                    'pose': 'Unspecified'
                })
                add_sub_node(x_object, 'bndbox', {
                    'xmin': detection['left'] + 1,
                    'xmax': detection['right'] + 1,
                    'ymin': detection['top'] + 1,
                    'ymax': detection['bottom'] + 1
                })

            ET.ElementTree(xml_root).write(f"{annotations_path}/{image_id}.xml")


def add_sub_node(node, name, kvs):
    subnode = ET.SubElement(node, name)
    for k, v in kvs.items():
        add_text_node(subnode, k, v)
    return subnode


def add_text_node(node, name, text):
    subnode = ET.SubElement(node, name)
    subnode.text = f"{text}"
    return subnode
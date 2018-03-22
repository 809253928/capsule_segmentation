# Copyright 2015 The TensorFlow Authors. All Rights Reserved.
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

"""Converts MNIST data to TFRecords file format with Example protos."""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import argparse
import os
import sys

import tensorflow as tf
import scipy.io as sio
import numpy as np
from sets import Set
import random
# from matplotlib import pyplot as plt

FLAGS = None


def _frame(img, max_h, max_w):
    row_range = (np.nonzero(img)[0].min(), np.nonzero(img)[0].max())
    col_range = (np.nonzero(img)[1].min(), np.nonzero(img)[1].max())

    framed_img = None
    if (row_range[1] - row_range[0] <= 28) and (col_range[1] - col_range[0] <= 28):
        framed_img = img[row_range[0]:row_range[1], col_range[0]:col_range[1]]
    return framed_img


def _get_d1_padding(total_padding):
    before = int(random.uniform(0, 1) * total_padding)
    after = total_padding - before
    return before, after


def _crop(img, height, width):
    framed_img = _frame(img, height, width)

    cropped_img = None
    if framed_img is not None:
        framed_shape = framed_img.shape
        padding1_d1 = _get_d1_padding(height - framed_shape[0])
        padding1_d2 = _get_d1_padding(width - framed_shape[1])
        cropped_img = np.pad(framed_img,
                             (padding1_d1, padding1_d2),
                             'constant', constant_values=((0, 0), (0, 0)))

    return cropped_img


def _int64_feature(value):
    return tf.train.Feature(int64_list=tf.train.Int64List(value=[value]))


def _bytes_feature(value):
    return tf.train.Feature(bytes_list=tf.train.BytesList(value=[value]))


def convert(images, labels, index):
    """Converts a dataset to tfrecords."""
    filename = os.path.join(FLAGS.dest, str(index) + '.tfrecords')
    print('Writing: %s, images num: %d' % (filename, len(images)))
    writer = tf.python_io.TFRecordWriter(filename)

    num_3 = 0
    num_5 = 0
    for i in range(len(images)):
        cropped_img = _crop(np.reshape(images[i], (40, 40)), 28, 28)

        if cropped_img is not None:
            # plt.imshow(cropped_img)
            # plt.xticks([]), plt.yticks([])  # to hide tick values on X and Y axis
            # plt.show()
            image = np.array(cropped_img, dtype=np.uint8)
            label = int(labels[i][0])

            if label in Set([3, 5]):
                image_raw = image.tostring()
                label_raw = np.array(np.where(image > 0, 1 if label == 3 else 2, 0), dtype=np.uint8).tostring()
                features = tf.train.Features(feature={
                    'height': _int64_feature(image.shape[0]),
                    'width': _int64_feature(image.shape[1]),
                    # 'name': _bytes_feature(name),
                    'image_raw': _bytes_feature(image_raw),
                    'label_raw': _bytes_feature(label_raw)})
                example = tf.train.Example(features=features)
                writer.write(example.SerializeToString())

                if label == 3:
                    num_3 += 1
                else:
                    num_5 += 1
    writer.close()

    return num_3, num_5


def main(unused_argv):
    data_dir, split = FLAGS.data_dir, FLAGS.split
    data = sio.loadmat(os.path.join(data_dir, split + '.mat'))

    images = data['affNISTdata'][0][0][2]
    labels = data['affNISTdata'][0][0][5]
    images_num = images.shape[1]

    start = 0
    end = min(FLAGS.file_size, images_num)
    total_num_3 = 0
    total_num_5 = 0
    i = 0
    while True:
        num_3, num_5 = convert(np.transpose(images[:, start:end]), np.transpose(labels[:, start:end]), i)
        print("File example num: %d, %d" % (num_3, num_5))
        total_num_3 += num_3
        total_num_5 += num_5
        if end < images_num:
            start = end
            end = min(end + FLAGS.file_size, images_num)
            i += 1
        else:
            break
    print("Total example num: %d, %d" % (total_num_3, total_num_5))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--data_dir',
        type=str,
        default='/tmp/data',
        help='Directory to download data files.'
    )
    parser.add_argument(
        '--split',
        type=str,
        default='validation',
        help='train, test or validation.'
    )
    parser.add_argument(
        '--dest',
        type=str,
        default='/tmp/data',
        help='Destination directory.'
    )
    parser.add_argument(
        '--file_size',
        type=int,
        help='The volume of each generated file.'
    )

    FLAGS, unparsed = parser.parse_known_args()
    tf.app.run(main=main, argv=[sys.argv[0]] + unparsed)
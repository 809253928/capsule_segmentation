from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import tensorflow as tf
from python.layers.convolution import conv2d, deconv
from python.layers.primary_capsules import primary_caps1d
from python.layers.conv_capsules import conv_capsule1d
from python.layers.class_capsules import class_caps1d


def inference(inputs, num_classes, routing_ites=3, remake=True, name='vector_net'):
    """

    :param inputs:
    :param num_classes:
    :param routing_ites:
    :param remake:
    :param name:
    :return:
    """

    with tf.variable_scope(name) as scope:
        inputs_shape = inputs.get_shape()
        batch_size = inputs_shape[0].value
        image_height = inputs_shape[2].value
        image_width = inputs_shape[3].value

        # ReLU Conv1
        # Images shape (b, 1, 24, 56) -> conv 5x5 filters, 32 output channels, strides 2 with padding, ReLU
        # nets -> (b, 256, 16, 48)
        print('inputs shape: %s' % inputs.get_shape())

        print("\nconv1 layer:")
        conv1 = conv2d(
            inputs,
            kernel=9, out_channels=256, stride=1, padding='VALID',
            activation_fn=tf.nn.relu, name='relu_conv1'
        )
        print('conv1 shape: %s' % conv1.get_shape())

        print("\nconv2 layer:")
        conv2 = conv2d(
            conv1,
            kernel=5, out_channels=256, stride=1, padding='VALID',
            activation_fn=tf.nn.relu, name='relu_conv2'
        )
        print('conv2 shape: %s' % conv1.get_shape())

        # PrimaryCaps
        # (b, 256, 16, 48) -> capsule 1x1 filter, 32 output capsule, strides 1 without padding
        # nets -> activations (?, 14, 14, 32))
        print("\nprimary layer:")
        primary_out_capsules = 28
        primary_caps_activations = primary_caps1d(
            conv2,
            kernel_size=5, out_capsules=primary_out_capsules, stride=1,
            padding='VALID', activation_length=8, name='primary_caps'
        )  # (b, 32, 4, 20, 8)

        print("\nconv capsule layer:")
        conv_out_capsules = 24
        conv_caps_activations = conv_capsule1d(
            primary_caps_activations, kernel_size=3,
            stride=2, routing_ites=routing_ites, in_capsules=primary_out_capsules,
            out_capsules=conv_out_capsules, batch_size=batch_size, name='conv_caps'
        )  # (b, 32*4*20, 8)

        # (b, 32, 4, 20, 8) -> # (b, 32*4*20, 2*64)
        print("\nclass capsule layer:")
        class_caps_activations, class_coupling_coeffs = class_caps1d(
            conv_caps_activations,
            num_classes=num_classes, activation_length=24, routing_ites=routing_ites,
            batch_size=batch_size, name='class_capsules')
        print('class_caps_activations shape: %s' % class_caps_activations.get_shape())

        # remakes_flatten = _remake(class_caps_activations, image_height * image_width) if remake else None
        remakes_flatten = None

        print("\ndecode layers:")
        label_logits = _decode(
            conv_caps_activations, conv_out_capsules,
            coupling_coeffs=class_coupling_coeffs,
            num_classes=num_classes, batch_size=batch_size)

        labels2d = tf.argmax(label_logits, axis=3)
        labels2d_expanded = tf.expand_dims(labels2d, -1)
        tf.summary.image('labels', tf.cast(labels2d_expanded, tf.uint8))

    return class_caps_activations, remakes_flatten, label_logits

def _remake(class_caps_activations, num_pixels):
    first_layer_size, second_layer_size = 672, 1344
    capsules_2d = tf.contrib.layers.flatten(class_caps_activations)

    remakes_flatten = tf.contrib.layers.stack(
        inputs=capsules_2d,
        layer=tf.contrib.layers.fully_connected,
        stack_args=[(first_layer_size, tf.nn.relu),
                    (second_layer_size, tf.nn.relu),
                    (num_pixels, tf.sigmoid)],
        reuse=False, scope='remake',
        weights_initializer=tf.truncated_normal_initializer(
            stddev=0.1, dtype=tf.float32),
        biases_initializer=tf.constant_initializer(0.1))

    return remakes_flatten  # (b, 1344)

def _decode(activations, capsule_num, coupling_coeffs, num_classes, batch_size):
    capsule_probs = tf.norm(activations, axis=-1)  # # (b, 32, 4, 20, 8) -> (b, 32, 4, 20)
    caps_probs_tiled = tf.tile(tf.expand_dims(capsule_probs, -1), [1, 1, 1, 1, num_classes])  # (b, 32, 4, 20, 2)

    print('coupling_coeffs shape: %s' % coupling_coeffs.get_shape())
    activations_shape = activations.get_shape()
    height, width = activations_shape[2].value, activations_shape[3].value
    coupling_coeff_reshaped = tf.reshape(coupling_coeffs, [batch_size, capsule_num, height, width, num_classes])  # (b, 32, 4, 20, 2)

    class_labels = tf.reduce_sum(coupling_coeff_reshaped * caps_probs_tiled, 1)  # (b, 4, 20, 2)
    # primary_labels = tf.reduce_sum(caps_probs_tiled, 1)
    deconv1 = deconv(
        class_labels,
        kernel=4, out_channels=num_classes, stride=2,
        activation_fn=tf.nn.relu, name='deconv1'
    )
    deconv2 = deconv(
        deconv1,
        kernel=5, out_channels=num_classes, stride=1,
        activation_fn=tf.nn.relu, name='deconv2'
    )
    deconv3 = deconv(
        deconv2,
        kernel=5, out_channels=num_classes, stride=1,
        activation_fn=tf.nn.relu, name='deconv3'
    )
    label_logits = deconv(
        deconv3,
        kernel=9, out_channels=num_classes, stride=1,
        activation_fn=tf.nn.relu, name='deconv4'
    )

    return label_logits


def loss(images, labels2d, class_caps_activations, remakes_flatten, label_logits, num_classes):
    """

    :param images:
    :param labels2d:
    :param class_caps_activations:
    :param remakes_flatten:
    :param label_logits:
    :param num_classes:
    :return:
    """

    with tf.name_scope('loss'):
        # with tf.name_scope('remake'):
        #     image_flatten = tf.contrib.layers.flatten(images)
        #     distance = tf.pow(image_flatten - remakes_flatten, 2)
        #     remake_loss = tf.reduce_sum(distance, axis=-1)
        #
        #     batch_remake_loss = tf.reduce_mean(remake_loss)
        #     balanced_remake_loss = 0.05 * batch_remake_loss
        #
        #     tf.add_to_collection('losses', balanced_remake_loss)
        #     tf.summary.scalar('remake_loss', balanced_remake_loss)

        # with tf.name_scope('margin'):
        #     labels_shape = labels2d.get_shape()
        #     num_pixels = labels_shape[1].value * labels_shape[2].value
        #
        #     class_caps_norm = tf.norm(class_caps_activations, axis=-1)  # (b, num_classes)
        #
        #     class_numbers = []
        #     for i in range(num_classes):
        #         class_elements = tf.cast(tf.equal(labels2d, i), tf.int32)  # (b, h, w)
        #         class_number = tf.reduce_sum(class_elements, [1, 2])  # (b)
        #         class_numbers.append(class_number)
        #
        #     class_probs = tf.divide(tf.stack(class_numbers, axis=1), num_pixels)  # (b, num_classes)
        #     margin_loss = tf.pow(tf.cast(class_probs, tf.float32) - class_caps_norm, 2)
        #
        #     batch_margin_loss = tf.reduce_mean(margin_loss)
        #     balanced_margin_loss = 10 * batch_margin_loss
        #
        #     tf.add_to_collection('losses', balanced_margin_loss)
        #     tf.summary.scalar('margin_loss', balanced_margin_loss)

        with tf.name_scope('decode'):
            cross_entropy = tf.nn.sparse_softmax_cross_entropy_with_logits(labels=labels2d,
                                                                           logits=label_logits)
            batch_decode_loss = tf.reduce_mean(cross_entropy)
            balanced_decode_loss = 5 * batch_decode_loss

            tf.add_to_collection('losses', balanced_decode_loss)
            tf.summary.scalar('decode_loss', balanced_decode_loss)



"""Tests the different convolution layers.

Mainly tests for shape correctness.

To run tests:
    `python tests.py`
"""

import unittest
import os
import argparse

os.environ["CUDA_VISIBLE_DEVICES"] = '0'
os.environ['TF_FORCE_GPU_ALLOW_GROWTH'] = 'true'

import tensorflow as tf
from tensorflow.keras.layers import Dense, Flatten, Conv2D
from tensorflow.keras import Model
from tensorflow.keras import datasets
import numpy as np

import convVariants

randomItem = np.random.random_sample
getShape = lambda input_: tuple(input_.shape)

class RegularModel(Model):
    def __init__(self, conv_layer):
        super(RegularModel, self).__init__()
        self.conv = conv_layer
        self.flatten = Flatten()
        self.d1 = Dense(128, activation='relu')
        self.d2 = Dense(10, activation='softmax')

    def call(self, x):
        x = self.conv(x)
        x = self.flatten(x)
        x = self.d1(x)
        return self.d2(x)

# @unittest.skip('Correct')
class TestCustomConv(unittest.TestCase):

    def load_data(self, max_instances, repeats, dataset='mnist'):

        channels_first = lambda x: np.transpose(x, [0, 3, 1, 2])

        if dataset == 'mnist':
            (x_train, y_train), (x_test, y_test) = datasets.mnist.load_data()
            x_train = x_train[:, tf.newaxis, :, :]
            x_test = x_test[:, tf.newaxis, :, :]
        elif dataset == 'cifar10':
            (x_train, y_train), (x_test, y_test) = datasets.cifar10.load_data()
            x_train = channels_first(x_train)
            x_test = channels_first(x_test)
        else:
            raise ValueError('Not a correct dataset.')

        x_train, x_test = x_train / 255.0, x_test / 255.0

        x_train = x_train[:max_instances]
        y_train = y_train[:max_instances]
        x_test = x_test[:max_instances]
        y_test = y_test[:max_instances]

        x_train = np.repeat(x_train, repeats=repeats, axis=1)
        x_test = np.repeat(x_test, repeats=repeats, axis=1)

        return x_train, y_train, x_test, y_test


    def run(
        self, 
        layer, 
        max_instances=1000, 
        EPOCHS=2, 
        repeats=1, 
        verbose=True):
        """This is just to check if the layer is backpropable.
        """
    
        x_train, y_train, x_test, y_test = self.load_data(
            max_instances,
            repeats)

        train_ds = tf.data.Dataset.from_tensor_slices(
            (x_train, y_train)).shuffle(1000).batch(32)

        test_ds = tf.data.Dataset.from_tensor_slices(
            (x_test, y_test)).batch(32)

        model = RegularModel(layer)

        loss_object = tf.keras.losses.SparseCategoricalCrossentropy()
        optimizer = tf.keras.optimizers.Adam()

        train_loss = tf.keras.metrics.Mean(name='train_loss')
        train_accuracy = tf.keras.metrics.SparseCategoricalAccuracy(
            name='train_accuracy')

        test_loss = tf.keras.metrics.Mean(name='test_loss')
        test_accuracy = tf.keras.metrics.SparseCategoricalAccuracy(
            name='test_accuracy')

        @tf.function
        def train_step(images, labels):
            with tf.GradientTape() as tape:
                predictions = model(images)
                loss = loss_object(labels, predictions)
            gradients = tape.gradient(loss, model.trainable_variables)
            optimizer.apply_gradients(zip(gradients, model.trainable_variables))

            train_loss(loss)
            train_accuracy(labels, predictions)

        @tf.function
        def test_step(images, labels):
            predictions = model(images)
            t_loss = loss_object(labels, predictions)

            test_loss(t_loss)
            test_accuracy(labels, predictions)

        for epoch in range(EPOCHS):
            for images, labels in train_ds:
                train_step(images, labels)

            for test_images, test_labels in test_ds:
                test_step(test_images, test_labels)

            if verbose:
                template = 'Epoch {}, Loss: {}, Accuracy: {}, \
                    Test Loss: {}, Test Accuracy: {}'
                print(template.format(epoch+1,
                    train_loss.result(),
                    train_accuracy.result()*100,
                    test_loss.result(),
                    test_accuracy.result()*100))

            # Reset the metrics for the next epoch
            train_loss.reset_states()
            train_accuracy.reset_states()
            test_loss.reset_states()
            test_accuracy.reset_states()

    
    def run2(self, layers, max_instances=1000, EPOCHS=2, repeats=1):
        """This doesn't work if output shapes are undetermined. """

        x_train, y_train, x_test, y_test = self.load_data(
            max_instances,
            repeats)

        # baseline layer:
        # Conv2D(32, 3, activation='relu')
        
        model = tf.keras.models.Sequential([])

        for layer in layers:
            model.add(layer)
        model.add(tf.keras.layers.Flatten())
        model.add(tf.keras.layers.Dense(128, activation='relu'))
        model.add(tf.keras.layers.Dropout(0.2))
        model.add(tf.keras.layers.Dense(10, activation='softmax'))


        model.compile(
            optimizer='adam',
            loss='sparse_categorical_crossentropy',
            metrics=['accuracy'])

        model.fit(x_train, y_train, epochs=EPOCHS)

        model.evaluate(x_test,  y_test, verbose=2)


    @unittest.skip('Correct')
    def test_AAConv(self):

        H = 36
        W = 54
        C_IN = 6
        C_OUT = 53
        B = 3
        kernel_size = 5
        depth_k = 16
        depth_v = 24
        num_heads = 8

        AAlayer = convVariants.AAConv(
            channels_out=C_OUT,
            kernel_size=kernel_size,
            depth_k=depth_k,
            depth_v=depth_v,
            num_heads=num_heads)

        input_shape = (B, C_IN, H, W)
        AAlayer.build(input_shape)

        x = randomItem((B, depth_k, H, W))
        result = AAlayer._split_heads_2d(x)
        self.assertEqual(
            getShape(result),
            (B, num_heads, H, W, depth_k // num_heads))

        x = randomItem((B, num_heads, H, W, depth_k // num_heads))
        result = AAlayer._combine_heads_2d(x)
        self.assertEqual(
            getShape(result),
            (B, H, W, depth_k))

        x = randomItem((B, C_IN, H, W))
        result = AAlayer._self_attention_2d(x)
        self.assertEqual(
            getShape(result),
            (B, depth_v, H, W))

        x = randomItem(input_shape)
        result = AAlayer(x)
        self.assertEqual(
            getShape(result),
            (B, C_OUT, H, W))

        layer = convVariants.AAConv(
            channels_out=32,
            kernel_size=3,
            depth_k=8, 
            depth_v=8, 
            num_heads=4)

        self.run(layer)

           
    @unittest.skip('Correct.')
    def test_MixConv(self):
        H = 36
        W = 54
        C_IN = 49
        C_OUT = 53
        B = 3

        expected_num_in_channels = [13, 12, 12, 12]
        input_shape = (B, C_IN, H, W)
        

        def check_depthwise(depthwise):

            kernel_sizes = [5, 7, 9, 11]
            layer = convVariants.MixConv(
                C_OUT, 
                kernel_sizes,
                depthwise=depthwise)
            layer.build(input_shape)

            result = layer._split_channels(C_IN, len(kernel_sizes))
            self.assertEqual(
                result,
                expected_num_in_channels)

            x = randomItem(input_shape)
            result = layer(x)
            self.assertEqual(
                getShape(result),
                (B, C_OUT, H, W))

            kernel_sizes = [(3, 3), (5, 5)]
            layer = convVariants.MixConv(
                C_OUT, 
                kernel_sizes,
                depthwise=depthwise,
                activation='relu')

            self.run2(
                [layer], 
                EPOCHS=5, 
                repeats=2, 
                max_instances=600)

        check_depthwise(True)
        check_depthwise(False)


    @unittest.skip('Correct.')
    def test_ChannelGate(self):
        H = 36
        W = 54
        C_IN = 49
        B = 3

        input_shape = (B, C_IN, H, W)

        layer = convVariants.ChannelGate(C_IN, reduction_ratio=3)
        
        x = randomItem(input_shape)
        result = layer(x)

        self.assertEqual(
            getShape(result),
            input_shape)


    @unittest.skip('Correct.')
    def test_SpatialGate(self):
        H = 36
        W = 54
        C_IN = 49
        B = 3

        input_shape = (B, C_IN, H, W)

        layer = convVariants.SpatialGate()

        x = randomItem(input_shape)
        result = layer(x)

        self.assertEqual(
            getShape(result),
            input_shape)


    @unittest.skip('Correct.')
    def test_CBAM(self):
        H = 36
        W = 54
        C_IN = 49
        C_OUT = 50
        B = 3
        kernel_size = (3,3)

        input_shape = (B, C_IN, H, W)

        layer = convVariants.CBAM(
            filters=C_OUT,
            reduction_ratio=3,
            kernel_size=kernel_size,
            padding='same')

        x = randomItem(input_shape)
        result = layer(x)

        self.assertEqual(
            getShape(result),
            (B, C_OUT, H, W))

        layer1 = Conv2D(
            filters=C_OUT, 
            kernel_size=kernel_size, 
            data_format='channels_first',
            activation='relu', 
            padding='same')

        layer2 = convVariants.CBAM(
            filters=C_OUT,
            reduction_ratio=2, 
            kernel_size=kernel_size,
            activation='relu',
            padding='same')

        self.run2(
            # [layer1, layer2], 
            [layer2],
            EPOCHS=5, 
            repeats=1, 
            max_instances=60000)


    @unittest.skip('Correct.')
    def test_ECA(self):
        H = 36
        W = 54
        C_IN = 49
        C_OUT = 50
        B = 3
        kernel_size = (3,3)

        input_shape = (B, C_IN, H, W)

        layer = convVariants.ECAConv(
            filters=C_OUT,
            eca_k_size=3,
            kernel_size=kernel_size,
            padding='same')

        x = randomItem(input_shape)
        result = layer(x)

        self.assertEqual(
            getShape(result),
            (B, C_OUT, H, W))


    @unittest.skip('Correct.')
    def test_DropBlock(self):
        H = 36
        W = H
        C_IN = 49
        C_OUT = 50
        B = 3
        kernel_size = (3,3)

        input_shape = (B, C_IN, H, W)

        layer = convVariants.DropBlock(0.95, 3)

        x = randomItem(input_shape)
        result = layer(x, training=True)
        self.assertEqual(
            getShape(result),
            input_shape)

        layer1 = Conv2D(
            filters=C_OUT, 
            kernel_size=kernel_size, 
            data_format='channels_first',
            activation='relu', 
            padding='same')
        
        layer2 = convVariants.DropBlock(0.90, 7)

        self.run2(
            [layer1, layer2], 
            # [layer1],
            EPOCHS=5, 
            repeats=1, 
            max_instances=60000)


    @unittest.skip('Correct.')
    def test_GroupConv(self):
        H = 36
        W = 54
        C_IN = 48
        C_OUT = 60
        B = 3
        kernel_size = (3,3)
        N_GROUPS = 6

        input_shape = (B, C_IN, H, W)

        layer = convVariants.GroupConv2D(
            filters=C_OUT, 
            kernel_size=kernel_size, 
            groups=N_GROUPS, 
            data_format='channels_first',
            padding="same",
            activation='relu')

        x = randomItem(input_shape)
        result = layer(x)

        self.assertEqual(
            getShape(result),
            (B, C_OUT, H, W))


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description='Testing custom convolution layers.')

    parser.add_argument(
        '-E', 
        action='store_true',
        default=False,
        help='Whether to test swith eager execution or not.')

    args = parser.parse_args()

    if args.E:
        print('Using Eager')
        tf.config.experimental_run_functions_eagerly(True)

    unittest.main()
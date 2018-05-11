import cv2
import numpy as np
from sklearn.metrics import accuracy_score


def dice(target_img, prediction_img, smooth=1.0):
    target = target_img.flatten()
    prediction = prediction_img.flatten()
    intersection = np.sum(np.multiply(target, prediction))
    union = np.sum(target) + np.sum(prediction)
    dice = (2.0 * intersection + smooth) / (union + smooth)

    return dice


def accuracy(target_img, prediction_img):
    accu_score = accuracy_score(target_img.flatten(), prediction_img.flatten())
    return accu_score


def add_noise(img, low, high):
    noise = cv2.randu(np.zeros(img.shape, np.uint8), low, high)
    img = cv2.add(img, noise)
    return img

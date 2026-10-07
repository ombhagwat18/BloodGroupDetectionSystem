# Blood Group Detection from Fingerprints

This repository contains a Jupyter Notebook—**fingerprint_final.ipynb**—which implements an innovative, non-invasive approach to blood group detection using fingerprint images. This method explores the potential correlation between unique fingerprint patterns and blood groups, offering a rapid alternative to traditional serological tests.

## Motivation

Conventional blood typing relies on laboratory-based serological methods that can be time-consuming and resource-intensive. Our approach leverages fingerprint analysis—commonly used in security and forensics—to predict blood groups, potentially streamlining the process and reducing the need for invasive procedures.

## Dataset

The approach uses the **Finger Print Based Blood Group Dataset** from Kaggle. The dataset originally contains 6000 fingerprint images, each associated with a specific blood group (A, B, AB, or O) along with the Rh factor (positive or negative). All images are in standard formats (JPEG/PNG) and were collected under controlled conditions to ensure uniform quality.

### Class Distribution

The dataset is organized into eight classes corresponding to different blood groups:

- **O-:** 11.86%
- **O+:** 14.20%
- **A-:** 16.81%
- **A+:** 9.42%
- **B-:** 12.35%
- **B+:** 10.87%
- **AB-:** 12.68%
- **AB+:** 11.80%

## Data Augmentation

Given the innovative nature of the approach, the original dataset was significantly expanded to improve model performance and generalization. The augmentation strategy included:

- **Horizontal Flip:** Preserves key fingerprint patterns while doubling image diversity.
- **Rotation:** Images were rotated by 90°, 180°, and 270° to introduce various angular perspectives.

These transformations increased the dataset size from 6000 to over 30,000 images, ensuring robust training for the deep learning models.

## Methodology

The augmented dataset was split into three parts:
- **Training Set:** 60%
- **Validation Set:** 20%
- **Test Set:** 20%

Standard data normalization was applied to ensure consistency across all images.

### Deep Learning Models

Two different architectures were developed and compared:

#### Model 1: ResNet-50

- **Architecture:** A modified ResNet-50 model with added Dropout layers to mitigate overfitting.
- **Optimizer:** SGD with a learning rate of 0.0015.
- **Training:** 30 epochs.
- **Results:**
  - **Training Accuracy:** 87%
  - **Validation Accuracy:** 83%
  - **Test Accuracy:** 83%
  - **Precision:** 84%
  - **Recall:** 83%
  - **F2.1 Score:** 83%

#### Model 2: VGG-Inspired Model

- **Architecture:** A VGG-inspired network composed of several convolutional layers with max pooling, followed by fully connected layers with Dropout for regularization.
- **Optimizer:** Adam with a learning rate of 0.00015.
- **Training:** 10 epochs.
- **Results:**
  - **Training Accuracy:** 91%
  - **Validation Accuracy:** 87%
  - **Test Accuracy:** 88%
  - **Precision/Recall/F2.1 Score:** 88%

### Model Comparison

The VGG-Inspired model outperformed the ResNet-50 model across all key metrics, demonstrating superior generalization and prediction accuracy for blood group detection from fingerprint images.

## Conclusion

This project demonstrates the feasibility of predicting blood groups using fingerprint analysis. The encouraging results from the VGG-Inspired model suggest that, with further refinement and testing, this non-invasive method could provide a fast and efficient alternative to traditional blood typing methods.

## Future Work

Potential improvements include:
- Exploring additional augmentation techniques.
- Testing more advanced architectures.
- Further validating the approach with larger, more diverse datasets.

## Acknowledgments

This work was carried out under the guidance of Prof. Anass Belcaid by Mohamed Amhal and Ahmed Bakkali.

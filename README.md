# Repository layout

## Extra_Files

Files that do not fit into just one of the themes present in the repository.

## Medium_example

Recreation of the project shown in this [article](https://medium.com/@rohith.sunkara/reconstructing-the-real-world-estimating-camera-position-from-images-and-gps-coordinates-6fd79009af28)

## Papers

Read papers for the making of the State of the Art.

## Prediction

A program that attempts to calculate the location of one or more points in a photo, taking into account their coordinates as well as the camera's coordinates and orientation.

## Thesis

Thesis document.

## Unity

An application built in Unity that accesses the mobile phone's camera and,  in the instant a photo is taken, saves data from various phone sensors, such as the compass, GPS, magnetometer, etc.

## Vision

Python scripts with various goals:\
    - Camera calibration with the aid of a checkerboard pattern;\
    - Projection of a cube onto the pattern to validate the calibration parameters;\
    - Attempt to calculate the location of the device that took a photo, taking into account a previously performed calibration, the coordinates of at least 3 points, and the positions of these points within the photo.
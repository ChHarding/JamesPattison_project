# JamesPattison_project
Project template for HCI 584, Python Application Development

#FitLens

FitLens is a fitness analytics dashboard that combines Apple Health export data with Hevy workout logs to give users a clearer, more actionable view of their training.

Most fitness data is scattered across multiple apps. Apple Health may track heart rate, HRV, resting heart rate, sleep, body stats, and VO2 max, while Hevy tracks strength workouts, sets, reps, volume, and exercise progression. FitLens brings those data sources together into one place and turns them into simple scores and trends that are easier to understand and act on.

# What FitLens Does

FitLens allows users to upload their Apple Health XML export and Hevy CSV workout export. The app parses both files, stores the data, and connects workout sessions with the matching Apple Health heart-rate data from those same time windows.

Using that combined dataset, FitLens calculates fitness, readiness, and progression insights over time.

Core Scores
Readiness Score

The readiness score is designed to estimate how prepared the user is for training based on recovery and recent strain.

It uses signals such as:

Heart rate variability
Resting heart rate
Sleep quality
Recent training load
Recent workout intensity
Fitness Score

The fitness score tracks overall fitness trends by combining cardiovascular, strength, and consistency metrics.

It may include:

VO2 max trend
Strength progression across logged lifts
Training consistency
Workout frequency
Long-term performance trends
Progression Score

The progression score focuses on whether the user’s training is moving in the right direction.

It analyzes Hevy workout data such as:

Training volume
Exercise intensity
Set and rep trends
Strength progression
Plateau detection
Potential overreaching signals
Dashboard

FitLens presents all of this information in a single dashboard with charts, score history, and trend summaries. The goal is to help users quickly understand whether they are improving, maintaining, plateauing, or pushing too hard.

# Data Import Flow

The initial version of FitLens uses file uploads rather than live API integrations.

Users upload:

An Apple Health XML export
A Hevy CSV workout export

FitLens then parses, normalizes, and stores the data. Users can periodically re-upload updated exports to refresh their dashboard and scores.

# Project Goal

The goal of FitLens is to turn raw fitness data into useful training feedback. Instead of forcing users to manually compare multiple apps, FitLens connects workout logs, recovery metrics, heart-rate data, and body stats into one clear picture of health and performance.
